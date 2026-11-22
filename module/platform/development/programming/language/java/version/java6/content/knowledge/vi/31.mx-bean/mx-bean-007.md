# Descriptor, DescriptorKey và metadata mở rộng của MXBean — Java 17+

## 1. Vì sao metadata cần thiết trong MXBean?

Một `MXBean` xuất bản attributes/operations qua Java Management Extensions (**JMX**) dưới dạng các kiểu dữ liệu có thể ánh xạ sang **Open Data**. Một dashboard hay công cụ quản trị có thể truy vấn `MBeanInfo`, phát hiện thuộc tính `Requests` kiểu `long` rồi hiển thị số hiện tại. Nhưng nó vẫn cần nhiều thông tin ngữ nghĩa khác:

- Đơn vị là requests, bytes, milliseconds hay phần trăm?
- Thuộc tính là **counter** tích lũy hay **gauge** tăng/giảm?
- Có khoảng `minValue`/`maxValue` nào được công bố cho người vận hành?
- Operation nhận tham số có ý nghĩa gì?
- Model này được cung cấp từ phiên bản nào?
- Dữ liệu Java gốc được chuyển thành Open Type ra sao?
- UI đọc field mở rộng của ứng dụng mà không phá tương thích với một JMX client thông thường như thế nào?

Các API hiện hành trong `java.management` giải quyết việc **mô tả**, không tự động **thực thi nghiệp vụ**:

1. **`Descriptor`:** tập các field dạng **name → value**, kèm một đối tượng thông tin JMX.
2. **`@DescriptorKey`:** meta-annotation chỉ rõ phần tử của một **custom annotation** đóng góp value vào field nào của Descriptor.
3. **`MBeanInfo` và các `MBean*Info`:** metadata của toàn MBean, attribute, operation, parameter, constructor hoặc notification; các class này có `getDescriptor()`.
4. **`ImmutableDescriptor` và `DescriptorSupport`:** hai cách lưu tập field bất biến và khả biến.
5. **MXBean Open Type descriptors:** các trường do JMX sinh (`mxbean`, `interfaceClassName`, `openType`, `originalType`) và những trường do ứng dụng tự thêm (`units`, `metricType`, `com.example.note`, v.v.).

**Mục tiêu:** hiểu đúng nơi đặt metadata; viết Java annotation có `@DescriptorKey`; đọc metadata ở mọi cấp; kiểm tra xung đột field; hiểu sự khác nhau giữa mô tả và kiểm tra hợp lệ; biên dịch/chạy được hai ví dụ trên **Java 17+**, phù hợp cả Java 21/25.

**Special Note áp dụng:** chỉ dùng kiến thức vẫn có hiệu lực trên JDK hiện đại. `Descriptor`/`DescriptorKey` từng được bổ sung vào JMX từ Java 6 nhưng không phải API lỗi thời; không cần xây lại với deprecated JDK internals, không khuyến khích mở remote JMX không có TLS/xác thực.

## 2. Descriptor là gì, gắn ở đâu?

`javax.management.Descriptor` là interface chứa tập field không phân biệt hoa/thường ở tên. Với một MXBean, sơ đồ:

```text
@MXBean interface CounterMXBean
          |
          | registerMBean(...)
          v
MBeanServer.getMBeanInfo(ObjectName)
          |
          +-- MBeanInfo.getDescriptor()
          |     mxbean = "true"
          |     interfaceClassName = "..."
          |     com.example.note = "In-process counter MXBean"
          |
          +-- MBeanAttributeInfo("Requests").getDescriptor()
          |     units = "requests"
          |     metricType = "counter"
          |     openType = SimpleType.LONG
          |
          +-- MBeanAttributeInfo("Threshold").getDescriptor()
          |     minValue = Integer(0)
          |     maxValue = Integer(100)
          |
          +-- MBeanOperationInfo("record").getDescriptor()
          |     com.example.note = "Add a positive batch"
          |
          +-- MBeanParameterInfo("amount").getDescriptor()
                com.example.note = "Positive batch size"
```

Sơ đồ này là cấu trúc **được chương trình ở mục 7 kiểm chứng**. Không nhầm các descriptor ở cấp khác nhau: field `com.example.note` của **MBeanInfo** khác field cùng tên trên **operation** hoặc **parameter**. Không có quy tắc tự động nhập mọi field từ MBean-level vào mọi attribute.

### 2.1. Các class cung cấp descriptor

| Đối tượng | Mục đích | Truy cập Descriptor |
| --- | --- | --- |
| `MBeanInfo` | Management model của toàn MBean. | `info.getDescriptor()` |
| `MBeanAttributeInfo` | Thuộc tính, Java/Open Data type, readable/writable. | `attribute.getDescriptor()` |
| `MBeanOperationInfo` | Operation, return type, impact và signature. | `operation.getDescriptor()` |
| `MBeanParameterInfo` | Metadata một tham số operation. | `operation.getSignature()[i].getDescriptor()` |
| `MBeanConstructorInfo` | Constructor metadata trong loại MBean phù hợp. | `constructor.getDescriptor()` |
| `MBeanNotificationInfo` | Loại notification mà MBean công bố. | `notification.getDescriptor()` |

Dù `MBeanServerConnection.getMBeanInfo(name)` có thể trả thông tin cho cả Standard MBean và MXBean, **không phải field nào cũng tồn tại trên mọi element**. Khi viết JMX collector, phải xử lý field null và type đúng, không lấy field ở cấp sai rồi coi kết quả là bug JVM.

### 2.2. Những phương thức quan trọng

```java
Descriptor descriptor = attribute.getDescriptor();

Object unit = descriptor.getFieldValue("units");
String[] fieldNames = descriptor.getFieldNames();
Object[] selected = descriptor.getFieldValues(
        "units", "metricType", "openType");
```

**Đây là snippet**, cần `MBeanAttributeInfo attribute` đã được đọc từ `MBeanInfo` và imports `javax.management.*`. Các methods hiện hành gồm:
- `getFieldValue(String)`, `getFieldNames()`, `getFields()` và `getFieldValues(String...)`;
- `setField`, `setFields`, `removeField` với descriptor **mutable**;
- `isValid()`, `clone()`, `equals()` và `hashCode()` theo contract.

Tên field **không phân biệt chữ hoa/thường**: `"units"` và `"UNITS"` tham chiếu cùng trường. Không đặt hai keys chỉ khác cách viết hoa. Giá trị mỗi trường là `Object`, **không phải mặc định String**: `openType` là `OpenType`; `minValue` từ annotation `int` là `Integer`; `mxbean` theo descriptor convention lại thường là String `"true"`.

### 2.3. Field chuẩn và custom field

| Field | Nơi thường gặp | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `mxbean` | `MBeanInfo` | String `"true"`/`"false"`; không cast Boolean. |
| `interfaceClassName` | `MBeanInfo` | Java management interface name theo `Class.getName()`. |
| `immutableInfo` | `MBeanInfo` | String `"true"` bảo đảm MBeanInfo không đổi trong lifetime của MBean khi được khai báo. |
| `infoTimeout` | `MBeanInfo` | Gợi ý thời gian metadata ít có khả năng thay đổi; không cưỡng chế cache. |
| `openType` | Attribute/operation/parameter | Đối tượng `OpenType` (ví dụ `SimpleType.LONG`). |
| `originalType` | Attribute/operation/parameter | Tên kiểu Java nguyên gốc của MXBean trước khi ánh xạ Open Data. |
| `units` | Attribute/operation/parameter | Đơn vị, ví dụ `"bytes"`, `"seconds"`, `"requests"`. |
| `metricType` | Attribute/operation | Theo convention `"counter"` hoặc `"gauge"`. |
| `minValue` / `maxValue` | Attribute/parameter | Giá trị biên nên cùng mapped type với dữ liệu, **không tự thực thi validation**. |
| `defaultValue` / `legalValues` | Attribute/parameter | Giá trị mặc định/tập values được mô tả cho client. |
| `since` / `deprecated` | Nhiều cấp | Version xuất hiện hoặc được khuyến nghị thay thế trong **management model**, không phải tuyên bố Java API đã bị xóa. |
| `descriptionResourceKey` | Nhiều cấp | Key để client có thể nội địa hóa mô tả khi hỗ trợ. |
| `descriptionResourceBundleBaseName` | Nhiều cấp | ResourceBundle name đi cùng key; JMX không tự translate cho mọi UI. |
| `severity` | Notification | Mức độ ưu tiên theo JMX convention. |
| `com.example.note` | Custom | Metadata ứng dụng tự đặt; client phải chủ động hiểu schema. |

Trong `javax.management.JMX` có constants cho các tên key chuẩn như `JMX.MXBEAN_FIELD`, `JMX.OPEN_TYPE_FIELD`, `JMX.ORIGINAL_TYPE_FIELD`. Khi định nghĩa tên custom, **nên chứa dấu chấm và namespace** (`com.example.note`, `org.acme.owner`). Javadoc cam kết các field names JMX định nghĩa trong những phiên bản tương lai sẽ không chứa dấu chấm, giảm nguy cơ va chạm.

### 2.4. Descriptor khác JavaBeans BeanDescriptor và JSON Schema

`javax.management.Descriptor` là metadata của **JMX MBeans**, không phải `java.beans.BeanDescriptor`, OpenAPI schema hay annotation processor. Cách đọc JMX là `getMBeanInfo()` và `getDescriptor()`; không cần reflection vào class nội bộ JVM hoặc parse `toString()` của MBeanInfo.

MXBean vẫn xuất bản **giá trị thực qua `getAttribute`/`invoke`**, còn Descriptor giúp công cụ hiểu ý nghĩa. Không dùng Descriptor để thay dữ liệu metric hiện tại hoặc lưu event history lớn.

## 3. @DescriptorKey là meta-annotation

Một điều dễ sai: **`@DescriptorKey` không phải annotation đặt trực tiếp lên getter của MXBean**. Nó đặt trên **method khai báo một phần tử của annotation khác**. Ví dụ:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Units {
    @DescriptorKey("units")
    String value();
}
```

Sau đó:

```java
@MXBean
public interface MetricsMXBean {
    @Units("requests")
    long getRequests();
}
```

Hai đoạn là **snippets**, cần imports. Khi interface trở thành MXBean, JMX xử lý `@Units("requests")` trên getter, lấy element `value()` do `@DescriptorKey("units")` đánh dấu, tạo field `units=requests` trong descriptor của attribute `Requests`.

**Bốn điều kiện cần nhớ:**
1. `@DescriptorKey` thuộc `javax.management` và chỉ dùng trên annotation element method theo `@Target(METHOD)` của chính nó.
2. Annotation ngoài như `@Units` cần `@Retention(RetentionPolicy.RUNTIME)` để introspector đọc được khi register.
3. `@Target` của annotation ngoài phải khớp nơi sử dụng (TYPE, METHOD, PARAMETER…).
4. Giá trị field phải nhất quán với annotations khác cùng cấp và fields được JMX implementation sinh.

### 3.1. Những nơi JMX đọc custom annotation

Theo hợp đồng Java 17 `DescriptorKey`:
- **Đúng Standard MBean hoặc MXBean interface** → trường tại `MBeanInfo`.
- **Method trong management interface** → attribute descriptor nếu getter/setter, operation descriptor nếu method là operation.
- **Parameter của operation method** → `MBeanParameterInfo` descriptor (không gộp vào attribute setter parameter).
- **Public constructor của implementation class**, và **parameter constructor** → constructor/parameter descriptors trong mô hình MBean hỗ trợ.
- **Các trường hợp khác bị bỏ qua** theo JMX introspection rules.

Đặt annotation lên **implementation class method** nhưng không đặt trên **management interface** không phải cách đáng tin để export field. Bài mẫu chủ ý gắn annotation vào `CounterMXBean` và những methods/parameters trong interface.

### 3.2. Kế thừa và override không giống kế thừa Java method thông thường

- Interface-level annotation được xem trên **chính management interface** được công bố, không tự nhập từ mọi parent interface.
- Với method override, chú thích được xét ở **most-specific interface method**; annotation từ parent có thể không đóng góp nếu child khai báo lại method.
- Khi refactor interface hierarchy, phải có integration test `getMBeanInfo` sau thay đổi. Không dựa vào việc một annotation có `@Inherited` để suy JMX sẽ tự kế thừa metadata trên interface.

### 3.3. Getter/setter phải nhất quán

Nếu getter và setter cùng mô tả thuộc tính `Threshold`:
- Getter gắn `@Bounds(min=0,max=100)`.
- Setter cũng gắn `@Bounds(min=0,max=100)`.
- `@Note("Alert threshold")` trên cả hai phải tương thích.

Nếu getter ghi `@Units("bytes")` và setter ghi `@Units("items")`, chúng mâu thuẫn về field `units` của **cùng attribute**. JMX không nên chọn một field ngẫu nhiên: đăng ký MXBean có thể bị `NotCompliantMBeanException`. Điều này đã được thực thi thành một negative test ở mục 8.

### 3.4. Chuyển kiểu annotation element thành descriptor value

| Annotation element | Descriptor field value |
| --- | --- |
| `String` | Giữ nguyên String. |
| Primitive `int`, `long`, `boolean`… | Wrapper `Integer`, `Long`, `Boolean`… |
| `String[]`, `int[]`… | Giá trị mảng cùng kiểu theo quy tắc. |
| `Class<?>` literal | Tên lớp từ `Class.getName()`, là String. |
| Enum constant | Tên enum từ `Enum.name()`, là String. |
| Mảng Class/enum | Mảng Strings được chuyển đổi từng phần tử. |
| Annotation hoặc array of annotations | **Không** hỗ trợ làm element chuyển thành Descriptor field. |

**Một custom annotation có thể có nhiều elements mang `@DescriptorKey`**, ví dụ `@Bounds` có cả `min()` và `max()`. Bạn không cần tạo một annotation riêng cho từng field nếu chúng thuộc một khái niệm thống nhất.

## 4. Descriptor của MXBean và Open Data mapping

MXBean ánh xạ kiểu Java của management interface sang **Open Data** để JMX clients có thể trao đổi mà không phải chia sẻ mọi implementation class. Điều này giải thích vì sao:
- `MBeanAttributeInfo` của MXBean có field `openType`;
- có thể có `originalType` giúp phân biệt Java type gốc với Open Type;
- `OpenType` của một `long` được biểu diễn bằng `SimpleType.LONG`;
- các loại phức tạp có thể được biểu diễn bằng `CompositeType`/`TabularType` và giá trị qua `CompositeData`/`TabularData` theo quy tắc mapping.

**Không suy tất cả Java object đều là Open Types hợp lệ.** Các constraints của MXBean type mapping phải được tuân thủ; nếu interface dùng kiểu không thể ánh xạ, MXBean có thể bị từ chối khi đăng ký hoặc truy vấn. Không dùng Java serialization tùy ý để vượt qua contract này.

### 4.1. Đừng nhầm metadata và enforcement

`@Metric("counter")` giúp dashboard biết giá trị đang biểu diễn counter, nhưng không làm counter tự tăng. `@Bounds(min=0,max=100)` giúp UI hiển thị phạm vi, nhưng **không phải một ACL hay validation engine áp dụng tự động cho mọi Attribute write**.

Trong code thật, setter phải kiểm tra:

```java
@Override
public synchronized void setThreshold(int value) {
    if (value < 0 || value > 100) {
        throw new IllegalArgumentException("0..100 only");
    }
    threshold = value;
}
```

**Snippet** nằm trong `Counter` ở mục 7. Cả validator và Descriptor đều có vai trò: **metadata thông báo**, **implementation thực thi quy tắc**. Đối với operations thay đổi trạng thái, áp dụng cả quyền/authorization bên ngoài logic đơn thuần.

### 4.2. Metric counter vs gauge

Theo JMX Descriptor convention:
- `metricType=counter`: số liệu đo thường tăng theo thời gian, trừ reset hoặc tràn/khởi tạo lại.
- `metricType=gauge`: một phép đo tăng giảm như queue depth, in-flight requests, memory usage.

Đây là **gợi ý cho tooling**, không tự đẩy metric vào Prometheus/OpenTelemetry hay bảo đảm backend sẽ hiểu custom field. Collector cần chủ động map metric semantics, units, resource identity, sampling intervals và cardinality.

### 4.3. Type-safe metadata consumer

```java
Object units = attribute.getDescriptor().getFieldValue("units");
if (units instanceof String unitText) {
    // Có thể dùng unitText sau khi validate/escape cho UI.
}
Object openType = attribute.getDescriptor().getFieldValue("openType");
if (openType instanceof javax.management.openmbean.OpenType<?> t) {
    // Chuyển dữ liệu theo t, không cast nhầm từ String.
}
```

**Snippet**: `attribute` có type `MBeanAttributeInfo`. Khi giá trị null hoặc type khác dự kiến, không crash toàn bộ dashboard; áp dụng fallback an toàn. Đừng render string tùy ý từ remote JMX thành HTML/raw JavaScript.

## 5. Thiết kế annotation metadata thực tế

Các annotation trong ví dụ chính:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
public @interface Note {
    @DescriptorKey("com.example.note")
    String value();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Metric {
    @DescriptorKey("metricType")
    String value();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Bounds {
    @DescriptorKey("minValue")
    int min();

    @DescriptorKey("maxValue")
    int max();
}
```

Những đoạn này là **định nghĩa annotation**, code hoàn chỉnh ở mục 7. `@Documented` chỉ điều khiển JavaDoc inclusion, không thay `@Retention(RUNTIME)`. `@Target` giới hạn những nơi Java compiler cho phép gắn custom annotation; JMX sau đó còn áp dụng quy tắc riêng về management interface/operations.

Một annotation `@Note` có thể đặt:
- Trên **MXBean interface** để tạo note trong `MBeanInfo`.
- Trên **getter/setter** để tạo note ở `MBeanAttributeInfo`.
- Trên **operation** để tạo note ở `MBeanOperationInfo`.
- Trên **operation parameter** để tạo note ở `MBeanParameterInfo`.

Hai phần tử `@DescriptorKey` của `@Bounds` sinh `Integer` 0 và 100. `@Units("requests")` và `@Metric("counter")` thuộc attribute `Requests`, chứ không tự đi vào toàn bộ MBeanInfo.

**Khuyến nghị đặt tên custom field:** dùng `com.example.note` hoặc namespace thực được tổ chức sở hữu. JMX không định nghĩa sẵn ý nghĩa cho field custom; định nghĩa schema rõ, version và fallback khi client cũ không biết key. Không đặt password, access token, secret key hoặc thông tin người dùng riêng tư trong annotation hay descriptor.

## 6. Kiến trúc chương trình kiểm chứng

Chương trình chạy trên một `MBeanServer` **in-process**:
1. Đăng ký `Counter` là `@MXBean CounterMXBean` với `ObjectName("example:type=Counter")`.
2. Lấy `MBeanInfo` từ `server.getMBeanInfo(name)`.
3. Tìm `Requests`, `Threshold`, `record` bằng tên, không dựa vào vị trí mảng.
4. Đọc và assert descriptor fields ở cấp MBean/attribute/operation/parameter.
5. Đọc `openType` và kiểm tra `SimpleType.LONG`.
6. `MBeanServer.invoke` gọi `record(3)`, đọc `Requests` để kiểm tra giá trị tăng từ 7 thành 10.
7. Cố đặt threshold 101 để kiểm tra **setter validation**, đặt 20 để xác minh cập nhật hợp lệ.
8. Tạo `DescriptorSupport` và `ImmutableDescriptor` để thử case-insensitive names và tính bất biến.
9. `unregisterMBean` trong `finally`.

**Điều không thực hiện:** mở JMX/RMI remote listener, scan network, đọc thông tin hệ thống nhạy cảm hoặc gọi management operations của JVM khác.

## 7. Mã Java 17+ chạy được: DescriptorMxBeanDemo.java

Tạo file **`DescriptorMxBeanDemo.java`** bằng UTF-8:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

import javax.management.Attribute;
import javax.management.Descriptor;
import javax.management.DescriptorKey;
import javax.management.ImmutableDescriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.MXBean;
import javax.management.ObjectName;
import javax.management.modelmbean.DescriptorSupport;
import javax.management.openmbean.SimpleType;

public final class DescriptorMxBeanDemo {

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD, ElementType.PARAMETER})
    public @interface Note {
        @DescriptorKey("com.example.note")
        String value();
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Units {
        @DescriptorKey("units")
        String value();
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Metric {
        @DescriptorKey("metricType")
        String value();
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Bounds {
        @DescriptorKey("minValue")
        int min();

        @DescriptorKey("maxValue")
        int max();
    }

    @MXBean
    @Note("In-process counter MXBean")
    public interface CounterMXBean {
        @Note("Recorded request count")
        @Units("requests")
        @Metric("counter")
        long getRequests();

        @Note("Alert threshold")
        @Bounds(min = 0, max = 100)
        int getThreshold();

        @Note("Alert threshold")
        @Bounds(min = 0, max = 100)
        void setThreshold(int value);

        @Note("Add a positive batch")
        long record(@Note("Positive batch size") int amount);
    }

    public static final class Counter implements CounterMXBean {
        private long requests = 7;
        private int threshold = 10;

        @Override
        public synchronized long getRequests() {
            return requests;
        }

        @Override
        public synchronized int getThreshold() {
            return threshold;
        }

        @Override
        public synchronized void setThreshold(int value) {
            if (value < 0 || value > 100) {
                throw new IllegalArgumentException("0..100 only");
            }
            threshold = value;
        }

        @Override
        public synchronized long record(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("positive only");
            }
            requests += amount;
            return requests;
        }
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer("example");
        ObjectName name = new ObjectName("example:type=Counter");
        server.registerMBean(new Counter(), name);

        try {
            MBeanInfo info = server.getMBeanInfo(name);
            MBeanAttributeInfo requests = Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("Requests"))
                    .findFirst().orElseThrow();
            MBeanAttributeInfo threshold = Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("Threshold"))
                    .findFirst().orElseThrow();
            MBeanOperationInfo operation = Arrays.stream(info.getOperations())
                    .filter(o -> o.getName().equals("record"))
                    .findFirst().orElseThrow();
            MBeanParameterInfo input = operation.getSignature()[0];

            Descriptor general = info.getDescriptor();
            Descriptor reqDesc = requests.getDescriptor();
            Descriptor thresholdDesc = threshold.getDescriptor();
            Descriptor opDesc = operation.getDescriptor();
            Descriptor paramDesc = input.getDescriptor();

            check("true".equals(general.getFieldValue("mxbean")),
                    "MXBean flag");
            check("In-process counter MXBean".equals(
                    general.getFieldValue("com.example.note")),
                    "interface note");
            check("requests".equals(reqDesc.getFieldValue("UNITS")),
                    "units");
            check("counter".equals(reqDesc.getFieldValue("metricType")),
                    "metric");
            check(SimpleType.LONG.equals(
                    reqDesc.getFieldValue("openType")),
                    "openType");
            check(Integer.valueOf(0).equals(
                    thresholdDesc.getFieldValue("minValue")),
                    "minimum");
            check(Integer.valueOf(100).equals(
                    thresholdDesc.getFieldValue("maxValue")),
                    "maximum");
            check("Add a positive batch".equals(
                    opDesc.getFieldValue("com.example.note")),
                    "operation note");
            check("Positive batch size".equals(
                    paramDesc.getFieldValue("com.example.note")),
                    "parameter note");

            System.out.println("registered=" + server.isRegistered(name));
            System.out.println("mxbeanFlag=" +
                    general.getFieldValue("mxbean"));
            System.out.println("interfaceNote=" +
                    general.getFieldValue("com.example.note"));
            System.out.println("attributeUnits=" +
                    reqDesc.getFieldValue("UNITS"));
            System.out.println("attributeMetricType=" +
                    reqDesc.getFieldValue("metricType"));
            System.out.println("openTypeLong=" +
                    SimpleType.LONG.equals(
                        reqDesc.getFieldValue("openType")));
            System.out.println("thresholdMin=" +
                    thresholdDesc.getFieldValue("minValue"));
            System.out.println("thresholdMax=" +
                    thresholdDesc.getFieldValue("maxValue"));
            System.out.println("operationNote=" +
                    opDesc.getFieldValue("com.example.note"));
            System.out.println("parameterNote=" +
                    paramDesc.getFieldValue("com.example.note"));

            Object total = server.invoke(name, "record",
                    new Object[] {3}, new String[] {input.getType()});
            check(Long.valueOf(10).equals(total), "operation result");
            System.out.println("recordResult=" + total);
            System.out.println("attributeRead=" +
                    server.getAttribute(name, "Requests"));

            boolean invalidRejected = false;
            try {
                server.setAttribute(name, new Attribute("Threshold", 101));
            } catch (Exception expected) {
                invalidRejected = true;
            }
            check(invalidRejected, "invalid setter must reject");
            server.setAttribute(name, new Attribute("Threshold", 20));
            System.out.println("invalidThresholdRejected=" +
                    invalidRejected);
            System.out.println("thresholdAfterSet=" +
                    server.getAttribute(name, "Threshold"));

            Descriptor mutable = new DescriptorSupport();
            mutable.setField("com.example.flag", "sample");
            Descriptor immutable = new ImmutableDescriptor(
                    new String[] {"com.example.flag"},
                    new Object[] {"locked"});

            boolean readonly = false;
            try {
                immutable.setField("com.example.flag", "changed");
            } catch (RuntimeException expected) {
                readonly = true;
            }
            check(readonly, "immutable descriptor cannot mutate");
            check("sample".equals(
                    mutable.getFieldValue("COM.EXAMPLE.FLAG")),
                    "case insensitive");
            System.out.println("fieldNamesIgnoreCase=" +
                    "sample".equals(
                        mutable.getFieldValue("COM.EXAMPLE.FLAG")));
            System.out.println("immutableDescriptorRejectedChange=" +
                    readonly);
        } finally {
            server.unregisterMBean(name);
        }
        System.out.println("unregistered=" + !server.isRegistered(name));
    }
}
```

### 7.1. Biên dịch/chạy

```bash
javac --release 17 -encoding UTF-8 DescriptorMxBeanDemo.java
java DescriptorMxBeanDemo
```

Code không cần Maven/Gradle. `javax.management` và `javax.management.openmbean` có sẵn trong JDK (`java.management`). Dự án JPMS có `module-info.java` cần khai báo `requires java.management;`. `@MXBean` xác định management interface; class `Counter` chỉ implement, không cần annotation trên mỗi implementation method.

Trong `MBeanServer.invoke`, signature của tham số được lấy từ `MBeanParameterInfo.getType()` vì MXBean có thể ánh xạ Java type sang Open Type representation. Đừng suy raw operation signature bằng tay khi viết generic collector.

### 7.2. Stdout xác minh thực tế

Hai file ví dụ trong bài đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và thực thi thành công trên JDK hiện đại. Với chương trình chính, **17 dòng stdout chính xác**:

```text
registered=true
mxbeanFlag=true
interfaceNote=In-process counter MXBean
attributeUnits=requests
attributeMetricType=counter
openTypeLong=true
thresholdMin=0
thresholdMax=100
operationNote=Add a positive batch
parameterNote=Positive batch size
recordResult=10
attributeRead=10
invalidThresholdRejected=true
thresholdAfterSet=20
fieldNamesIgnoreCase=true
immutableDescriptorRejectedChange=true
unregistered=true
```

Chúng chứng minh:
- Descriptor **MBean-level** chứa `mxbean=true` và note từ annotation trên interface.
- Attribute `Requests` có `units=requests`, `metricType=counter` và `openType=SimpleType.LONG`.
- Attribute `Threshold` có `minValue`/`maxValue` đúng kiểu Integer.
- Operation `record` và parameter riêng lẻ mang `com.example.note` đúng cấp.
- Cùng một attribute được đọc/gọi qua `MBeanServer`, và setter validation thực sự từ chối 101.
- `DescriptorSupport` field lookup không phân biệt hoa/thường, `ImmutableDescriptor` không cho sửa.
- MXBean được unregister sau khi test.

**Không suy ra JMX remote được bảo vệ** từ output: đây là JMX local trong cùng JVM, chưa mở connector.

## 8. Negative test có thể chạy: metadata getter/setter không nhất quán

Ví dụ tiếp theo kiểm tra quy tắc consistency của `@DescriptorKey`. Getter và setter của cùng một attribute `Size` không được khai báo hai `units` khác nhau.

File **`DescriptorConflictDemo.java`**:

```java
import java.lang.annotation.*;
import javax.management.*;

public final class DescriptorConflictDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Units {
        @DescriptorKey("units")
        String value();
    }

    @MXBean
    public interface BadMXBean {
        @Units("bytes")
        int getSize();

        @Units("items")
        void setSize(int value);
    }

    public static final class Bad implements BadMXBean {
        private int size;

        public int getSize() {
            return size;
        }
        public void setSize(int value) {
            size = value;
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        boolean conflictRejected = false;

        try {
            server.registerMBean(new Bad(),
                    new ObjectName("example:type=Bad"));
        } catch (NotCompliantMBeanException expected) {
            conflictRejected = true;
        }
        if (!conflictRejected) {
            throw new AssertionError(
                    "Conflicting descriptor units must fail");
        }
        System.out.println(
                "conflictingGetterSetterUnitsRejected=" +
                conflictRejected);
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 DescriptorConflictDemo.java
java DescriptorConflictDemo
```

Kết quả **đã biên dịch và chạy**, đúng một dòng:

```text
conflictingGetterSetterUnitsRejected=true
```

Đây là ví dụ **cố tình sai** để minh họa registration failure, không phải thiết kế MXBean nên dùng. Nếu registration fail sau khi sửa annotations, phải đọc error/cause trước khi tìm đến remote JMX config — lỗi có thể xuất phát ngay ở introspection consistency.

## 9. ImmutableDescriptor, DescriptorSupport và metadata lifecycle

### 9.1. ImmutableDescriptor

`javax.management.ImmutableDescriptor` cung cấp descriptor bất biến:

```java
Descriptor immutable = new ImmutableDescriptor(
        new String[] {"com.example.note"},
        new Object[] {"fixed"});

Object text = immutable.getFieldValue("com.example.note");
// immutable.setField("com.example.note", "changed") sẽ bị từ chối.
```

**Snippet:** cần import `javax.management.Descriptor` và `ImmutableDescriptor`. `MBeanInfo.getDescriptor()` và các `MBeanFeatureInfo.getDescriptor()` thường cung cấp immutable descriptor hoặc bản copy. **Thao tác sửa object trả về không có nghĩa metadata đã publish trong MBeanServer được thay đổi**.

### 9.2. DescriptorSupport

`javax.management.modelmbean.DescriptorSupport` là một triển khai mutable Descriptor vẫn được Java hỗ trợ. Nó hay được nhắc cùng Model MBean nhưng ở đây chỉ làm ví dụ so sánh:

```java
Descriptor mutable = new DescriptorSupport();
mutable.setField("com.example.flag", "sample");

Object value = mutable.getFieldValue("COM.EXAMPLE.FLAG");
// value.equals("sample") là true.
```

**Snippet:** không có nghĩa phải chuyển từ MXBean sang Model MBean mới dùng metadata mở rộng. Đối với MXBean dựa trên annotations, dùng `@DescriptorKey` thường trực tiếp và rõ ràng hơn để tạo những fields tĩnh.

### 9.3. Metadata không phải mutable state

- `MBeanInfo` mô tả **management contract**.
- `getAttribute` đọc **giá trị runtime** của attribute.
- `setAttribute` và `invoke` có thể thay đổi state nếu caller được phép.
- `getDescriptor()` chỉ trả metadata, không thay thế những operation này.

Nếu metadata thực sự động, `DynamicMBean.getMBeanInfo()` có thể công bố cấu trúc phù hợp lifecycle của MBean. JMX có quy ước `immutableInfo`, `infoTimeout` và notification `jmx.mbean.info.changed` hỗ trợ client cân nhắc cache/refresh, nhưng **không tự động có notification khi bạn sửa file hoặc thay một Descriptor copy**. Thiết kế API rõ hơn thay vì “đẩy cập nhật” bằng side effect trên object đọc ra.

## 10. JMX client đọc metadata thế nào?

Với `MBeanServerConnection connection` và `ObjectName objectName` đã có từ connector được xác thực:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    Descriptor d = attribute.getDescriptor();
    Object units = d.getFieldValue("units");
    Object openType = d.getFieldValue("openType");

    // Kiểm tra null/type trước khi hiển thị hoặc map sang metrics.
}
```

**Snippet:** không tạo connector remote ở đây. `MBeanServerConnection` là API phù hợp để lấy metadata cả local/remote; `getMBeanInfo` khác `getAttribute` và `invoke`.

Một client generic nên:
1. Đọc `MBeanInfo` và xác định fields ở từng cấp đúng.
2. Không tin thứ tự `getAttributes()`/`getOperations()` có ý nghĩa; tìm theo tên, signature.
3. Kiểm tra `instanceof String` cho `units`/`metricType`, `instanceof OpenType<?>` cho `openType`.
4. Kiểm tra null/missing values thay vì cast mù quáng.
5. Không tự gọi operations có side effects chỉ vì đọc được metadata.
6. Escape các custom text fields trước khi render ở dashboard; validate URL scheme/hosts nếu field dùng như runbook link.
7. Khi metadata không thay đổi, cache theo `immutableInfo`/`infoTimeout` và chính sách của ứng dụng; khi thay đổi, refresh đúng cách.
8. Với custom field, document schema/version và fallback cho clients cũ.

### 10.1. Khi nào dùng MXBean proxy?

`JMX.newMXBeanProxy(connection, objectName, Interface.class)` phù hợp khi ứng dụng client **có quản lý interface Java** và muốn gọi các methods theo typed proxy. Nhưng một exporter generic hoặc dashboard chỉ muốn khám phá attributes có thể dùng `getMBeanInfo`/Open Type mapping mà không biết application classes. Proxy không tự đọc và chuyển custom Descriptor fields thành property trên object local.

### 10.2. Mô tả unit để phục vụ observability

Một exporter có thể đọc:
- `metricType` để phân biệt counter/gauge.
- `units` để thiết kế measurement unit.
- `openType` để biết scalar/composite/table.
- `com.example.note` để tạo tooltip mô tả.

Nhưng exporter phải **thật sự implement** các quy tắc trên, không trông đợi JMX tự gửi dữ liệu sang Prometheus/OpenTelemetry. Tránh dùng attribute tên runtime/user ID làm unbounded label; chọn cardinality và sampling interval hợp lý.

## 11. Bảo mật: metadata không phải quyền truy cập

### 11.1. JMX local không đồng nghĩa remote

`MBeanServerFactory.newMBeanServer(...)` tạo một server trong process. Nó **không** tự mở remote RMI/JMX port. Nếu production bật JMX remote agent/connector, cần:
- Network isolation/firewall và không expose Internet tùy tiện.
- Authentication, authorization phân quyền đọc vs thao tác.
- TLS/mTLS nếu transport đòi hỏi; quản lý certificates/secrets đúng.
- Audit các management operations.
- Hạn chế operations nguy hiểm (restart, reload, purge) và quyền invoke.

**Không dùng** cấu hình remote JMX thiếu xác thực hoặc TLS chỉ để kết nối thử nhanh trên production. Một custom field `com.example.note=admin only` chỉ là string, **không** chặn được caller không được phép nếu connector/JMX policy bị cấu hình sai.

### 11.2. Không đưa secret vào Descriptor

Metadata có thể được đọc bởi tools/client có quyền introspection. Không đặt password, token, connection strings có credentials, PII, internal-only network topology hoặc raw stack traces vào `@Note`/`Descriptor`. Nếu client render custom note thành HTML, cần escape để tránh XSS. Nếu custom metadata chứa runbook URL, giới hạn URI scheme và danh sách domain tin cậy.

### 11.3. Access control thuộc implementation hoặc JMX connector

`minValue` không là validation; `metricType` không là permission; `getImpact()` của operation chỉ mô tả loại tác động. Implementation và lớp quản trị phải thực sự kiểm tra inputs, quyền và resource scope. Khi method có side effect, không chỉ dựa trên nó có JMX annotation nào.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách đúng |
| --- | --- | --- |
| Custom field không xuất hiện | Annotation thiếu `RUNTIME` hoặc đặt trên implementation thay vì MXBean interface. | Đặt annotation tại management interface/method/parameter, test `getMBeanInfo`. |
| Không thể đặt `@DescriptorKey` lên getter | Nó có target annotation METHOD, dành cho annotation element. | Tạo custom annotation `@Units`, đánh dấu `value()`, rồi dùng `@Units` trên getter. |
| Annotation ở parent interface bị mất khi override | JMX xét most-specific interface method. | Annotate override và test. |
| Getter và setter có `units` khác nhau | Descriptor consistency conflict. | Giữ cùng value, không tạo mâu thuẫn; test registration. |
| `getFieldValue("units")==null` | Đọc descriptor sai cấp, hoặc field chưa được sinh. | Tìm `MBeanAttributeInfo` của getter, đọc descriptor đúng. |
| `ClassCastException` khi đọc `minValue` | Value từ `int` annotation là `Integer`; kiểu khác bị ép sai. | Check runtime type, dùng wrapper đúng. |
| `mxbean` được so với Boolean.TRUE | Trường chuẩn là String `"true"`. | So String hoặc dùng chuẩn JMX. |
| Cast `openType` thành String | `openType` là `OpenType`. | Dùng `SimpleType`/`CompositeType`/`TabularType`. |
| Metadata `maxValue=100` nhưng setter nhận 101 | Metadata không tự enforcement mọi đường. | Viết validation trong setter/operation. |
| `ImmutableDescriptor.setField` ném lỗi | Object bất biến. | Tạo descriptor mới/lifecycle thích hợp, không mutate. |
| Sửa descriptor nhận qua `getMBeanInfo` nhưng MBean không đổi | Object là immutable hoặc copy. | Quản lý metadata bằng đúng API/lifecycle. |
| `invoke` operation báo sai signature | MXBean type mapping sang Open Data. | Xem `MBeanOperationInfo.getSignature()`. |
| JMX UI không hiểu `com.example.note` | Custom field không thuộc UI standard. | UI có hỗ trợ schema riêng hoặc bỏ qua an toàn. |
| Remote JMX không an toàn | Connector/agent thiếu auth/TLS, không liên quan Descriptor. | Áp dụng authn/authz/TLS/ACL và audit. |
| Logs nhiều dữ liệu nhạy cảm | Metadata chứa secrets/PII. | Sanitize và giới hạn fields. |

**Quy trình debug:** kiểm tra MXBean registered name → interface/type mapping → đọc `MBeanInfo` → chọn đúng attribute/operation/signature → đọc descriptor theo cấp → so retention/target → test getter/setter conflicts → test thực tế setter/operation → kiểm tra quyền JMX remote nếu vấn đề chỉ xuất hiện ngoài process.

## 13. Test matrix: xác minh metadata bằng JMX

| Test | Đầu vào | Kết quả |
| --- | --- | --- |
| MXBean registration | `CounterMXBean` + `Counter` | `registerMBean` thành công. |
| MBean-level descriptor | `@Note` trên interface | `com.example.note` được đọc từ `MBeanInfo`. |
| MXBean flag | `@MXBean` interface | `mxbean` có String value `"true"`. |
| Attribute units | `@Units("requests")` trên getter | `Requests` descriptor có `units=requests`. |
| Metric type | `@Metric("counter")` | `metricType=counter`. |
| Open Type | `long getRequests()` | `openType=SimpleType.LONG`. |
| Bounds | `@Bounds(min=0,max=100)` | Integer 0 và 100. |
| Operation note | `@Note` trên `record` | Operation descriptor đúng. |
| Parameter note | `@Note` trên `amount` | Parameter descriptor đúng. |
| Case insensitivity | Field `units` truy vấn bằng `UNITS` | Cùng giá trị. |
| Actual operation | `record(3)` từ 7 | Trả 10, attribute Requests thành 10. |
| Setter invalid | `set Threshold=101` | Bị implementation từ chối. |
| Setter valid | `set Threshold=20` | Đọc lại thành 20. |
| Descriptor immutable | `setField` trên `ImmutableDescriptor` | Bị từ chối. |
| Getter/setter conflict | `@Units("bytes")` vs `@Units("items")` | `NotCompliantMBeanException`. |
| Missing custom fields | Field không khai báo | null hoặc fallback an toàn. |
| Remote authorization | Client thiếu quyền | Không thể invoke operation có side effect. |
| Metadata cache | `immutableInfo`/`infoTimeout` | Tuân đúng semantics khi client cache. |

**Không thử negative tests bằng production MXBean có operations nguy hiểm**. Chạy trong MBeanServer độc lập như chương trình mẫu.

## 14. Bài tập thực hành

1. Tạo `@Owner` với `@DescriptorKey("com.example.owner")` trên interface; assert field xuất hiện trong `MBeanInfo`.
2. Thêm `getQueueDepth()` và `@Metric("gauge")`, `@Units("items")`; phân biệt counter/gauge ở tooling.
3. Định nghĩa annotation có `Class<?>` và enum elements, kiểm tra field value chuyển thành tên class/tên enum.
4. Viết helper `readDescriptorValue(Descriptor d, String key, Class<T> expected)` để xử lý null/type an toàn.
5. Test child MXBean interface override getter và giữ/loại `@Units`; quan sát most-specific interface rule.
6. Thêm `@Bounds` cho operation parameter; implement validation trong operation và test input không hợp lệ.
7. Dùng `CompositeType`/`CompositeData` cho một MXBean attribute phức tạp; quan sát `openType` và `originalType`.
8. Viết một metadata exporter read-only, không invoke operations; escape custom descriptions trước render.
9. Thêm `since` hoặc `com.example.modelVersion` và test client cũ với fields mới.
10. Tạo DynamicMBean có metadata thay đổi và test cache/notification policy thay vì sửa trực tiếp descriptor copy.
11. Dùng permission model ở connector/agent riêng trong môi trường được phép, không mở remote JMX không bảo vệ.

## 15. FAQ

**1. Descriptor có phải annotation không?** Không, `Descriptor` là interface chứa name/value fields. `@DescriptorKey` là meta-annotation dùng để biến phần tử của custom annotation thành field.

**2. Vì sao cần `@Retention(RUNTIME)`?** JMX introspects annotation tại runtime lúc xây metadata; annotation bị mất sau compile sẽ không thể đóng góp field.

**3. DescriptorKey có bị deprecated trong Java 17/25?** Không, là API được hỗ trợ thuộc `java.management`.

**4. Dùng `@DescriptorKey` trực tiếp trên getter được không?** Không. Đặt trên method của annotation như `Units.value()`, rồi gắn `@Units` lên getter.

**5. Custom field được đặt tên gì?** Dùng namespace có dấu chấm như `com.example.note`, không trùng fields chuẩn và rõ type/semantics.

**6. Tôi phải gắn annotation ở class implementation hay interface?** Trên management interface và methods/operation parameters theo rules của `DescriptorKey`.

**7. Getter và setter cùng field có thể khác nhau không?** Không, metadata của attribute phải nhất quán; code negative test cho thấy registration bị từ chối.

**8. `units` có tự đổi số requests thành bytes không?** Không. Nó chỉ mô tả đơn vị; code/exporter phải áp dụng semantics.

**9. `minValue` có tự chặn setter không?** Không nên giả định. Setter phải validate; bài minh họa tự chặn value 101.

**10. `metricType=counter` có xuất Prometheus metric tự động không?** Không. Exporter cần map field và giá trị thực.

**11. Vì sao `mxbean` là String `"true"`?** Đó là kiểu field được JMX chuẩn hóa; đừng cast Boolean.

**12. `openType` khác `originalType` thế nào?** `openType` là kiểu Open Data đã mapped; `originalType` mô tả kiểu Java gốc của MXBean interface.

**13. `getFieldValue("UNITS")` có đọc field `units` không?** Có, field names case-insensitive.

**14. `ImmutableDescriptor` có thể cập nhật bằng setField không?** Không; muốn metadata mới phải tạo cấu trúc mới và publish qua đúng lifecycle.

**15. Có thể thấy field custom trong mọi UI JMX không?** Không mặc định. UI/collector phải hiểu custom key.

**16. Tạo `MBeanServerFactory.newMBeanServer` có mở JMX TCP/RMI port không?** Không; remote connector là cấu hình riêng.

**17. Có thể coi annotation là kiểm soát quyền invoke không?** Không; authorization phải có ở connector/MBeanServer/application.

**18. Chạy ví dụ bằng Java 17/21/25 cần dependency ngoài không?** Không, toàn bộ code dùng `java.management` và Java language/API đã có trong JDK 17.

## 16. Checklist triển khai

- [ ] Xác minh management interface thật sự là MXBean, Open Type mapping đúng.
- [ ] Dùng `Descriptor`/`DescriptorKey` và `MBeanInfo` trong `java.management`, tránh JDK internal APIs.
- [ ] Đặt custom annotation `@Retention(RUNTIME)`, `@Target` đúng cấp.
- [ ] Đặt `@DescriptorKey` trên annotation element, không phải trực tiếp lên MXBean method.
- [ ] Gắn metadata trên interface/getter/setter/operation/operation parameter theo quy tắc.
- [ ] Getter/setter và mọi annotations không xung đột field values.
- [ ] Custom field có dấu chấm/namespace và documented schema.
- [ ] Đọc `MBeanInfo` đúng cấp bằng `MBeanServerConnection.getMBeanInfo`.
- [ ] Kiểm tra field null/type, phân biệt String vs Integer vs OpenType.
- [ ] Không dùng `minValue`/`metricType` như enforcement/permission.
- [ ] Validate setters/operations bằng implementation và authorizations tương ứng.
- [ ] Không đổi `ImmutableDescriptor` hay copy rồi coi đã sửa metadata published.
- [ ] Với metadata động, chọn `DynamicMBean`/notification/cache policy rõ.
- [ ] Dùng Java 17+ tương thích JDK 21/25, không dùng API đã bỏ.
- [ ] Không đưa secrets/PII vào JMX metadata; escape custom text ở UI.
- [ ] Remote JMX cần authentication, authorization, TLS/network controls, auditing.
- [ ] Có positive/negative registration tests và metadata readback tests.

## 17. Tài liệu tham khảo chính thức

- [Java 17 — Descriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/Descriptor.html): field names/values và standard/conventional fields.
- [Java 25 — Descriptor](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/Descriptor.html): API còn hỗ trợ, nguyên tắc namespace cho custom fields.
- [Java 17 — DescriptorKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/DescriptorKey.html): meta-annotation, retention/target, contexts, consistency/inheritance và kiểu chuyển đổi.
- [Java 25 — DescriptorKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/DescriptorKey.html): xác nhận API cập nhật.
- [Java 17 — MXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html): JMX MXBean model.
- [Java 17 — MBeanInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanInfo.html): descriptor của MBean.
- [Java 17 — MBeanAttributeInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanAttributeInfo.html): descriptor attributes.
- [Java 17 — MBeanOperationInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanOperationInfo.html): operation descriptor.
- [Java 17 — MBeanParameterInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanParameterInfo.html): parameter descriptor.
- [Java 17 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanServerConnection.html): metadata introspection qua connection.
- [Java 17 — ImmutableDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/ImmutableDescriptor.html): descriptor bất biến.
- [Java 17 — DescriptorSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/modelmbean/DescriptorSupport.html): mutable descriptor.
- [Java 17 — SimpleType](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/openmbean/SimpleType.html): Open Type mapping.
- [Java 17 — JMX](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/JMX.html): standard field constants.
