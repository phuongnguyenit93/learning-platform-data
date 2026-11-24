# Attribute expression và type conversion với JMX adapter trong Spring Integration

## 1. Bài toán: đọc được attribute chưa đủ để xử lý đúng dữ liệu

**JMX (Java Management Extensions)** cho phép một ứng dụng Java công bố các **managed attribute** trên MBean để hệ thống quản trị đọc trạng thái như số message đang chờ, số kết nối, dung lượng bộ nhớ hoặc tình trạng sức khỏe của một thành phần. Spring Integration có **JMX attribute-polling inbound channel adapter** để định kỳ đọc một attribute và tạo `Message<?>` chứa giá trị đó. Trong module **`SPRING_INTEGRATION_ADAPTERS`**, kết quả có thể được chuyển tiếp tới `MessageChannel`, filter, transformer, router hoặc các adapter kết nối file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu.

Vấn đề thực tế là **giá trị JMX không phải lúc nào cũng có kiểu, đơn vị và cấu trúc phù hợp với bước kế tiếp**. Ví dụ, MBean công bố số message chờ dưới dạng chuỗi `"125"`, nhưng bộ lọc của hệ thống cần so sánh với ngưỡng số học `100`. Nếu biểu thức dùng `payload > 100` trên chuỗi, kết quả có thể sai hoặc lỗi vì so sánh không nhất quán về kiểu. Một số MBean còn trả về `CompositeData` hoặc `TabularData` thay vì Java bean đơn giản.

Bài này tập trung vào **attribute expression và type conversion**: phân biệt cách chọn attribute trong JMX với cách đánh giá biểu thức **SpEL** trên payload, cách xác định kiểu JMX thực tế, chuẩn hóa dữ liệu rồi mới áp dụng quy tắc nghiệp vụ.

```mermaid
flowchart LR
    A[MBean: PendingCountText = "125"] --> B[JMX attribute-polling adapter]
    B -->|String "125"| C[MessageChannel raw]
    C --> D[SpEL transformer: String thành Long]
    D -->|Long 125| E[SpEL filter: >= 100]
    E -->|Đạt ngưỡng| F[Alert / HTTP / Kafka / JMS]
```

## 2. Ba lớp cần phân biệt: tên attribute, biểu thức và chuyển kiểu

Trong một cấu hình tích hợp, ba khái niệm sau dễ bị nhầm lẫn:

| Lớp | Câu hỏi cần trả lời | Ví dụ | Thời điểm áp dụng |
| --- | --- | --- | --- |
| **JMX attribute selection** | Đọc thuộc tính nào của MBean nào? | `object-name="demo.integration:type=Queue,name=Orders"`, `attribute-name="PendingCountText"` | Khi poller truy cập JMX |
| **Attribute value expression** | Dùng giá trị đọc được để tính toán/ra quyết định thế nào? | SpEL `payload >= 100` trên payload kiểu số | Khi transformer/filter/router xử lý message |
| **Type conversion** | Chuyển giá trị sang kiểu và đơn vị mà luồng yêu cầu ra sao? | Chuỗi `"125"` thành `Long 125` | Trước bước tính toán, so sánh, serialize hoặc gửi tiếp |

Trong namespace JMX được tài liệu Spring Integration mô tả, `<int-jmx:attribute-polling-channel-adapter>` dùng **`attribute-name`** (tên thuộc tính) và **`object-name`** (tên MBean). Không nên tự thêm thuộc tính XML `attribute-expression` với giả định đây là SpEL chạy mỗi lần poll; hãy dùng transformer/filter của Spring Integration để đánh giá biểu thức trên dữ liệu sau khi đọc.

Ví dụ cấu hình nguồn:

```xml
<int-jmx:attribute-polling-channel-adapter
    id="ordersPendingSource"
    channel="rawPendingCount"
    mbean-server="mbeanServer"
    object-name="demo.integration:type=Queue,name=Orders"
    attribute-name="PendingCountText">
    <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
```

Giả sử MBean trả về chuỗi `"125"`, adapter sẽ tạo message có `payload` tương ứng. Bước chuẩn hóa độc lập:

```xml
<int:transformer
    input-channel="rawPendingCount"
    output-channel="numericPendingCount"
    expression="T(java.lang.Long).valueOf(payload.trim())"/>
```

Ở đây `payload` là payload của **message được transformer nhận**, `T(java.lang.Long)` là tham chiếu kiểu Java trong SpEL, còn `valueOf(...)` thực hiện chuyển đổi tường minh. Nếu JMX trả về `Long` hoặc `Integer` ngay từ đầu thì có thể bỏ bước parse chuỗi và so sánh số trực tiếp.

## 3. Kiểu dữ liệu của một JMX attribute đến từ đâu?

JMX công bố metadata cho từng attribute trong `MBeanInfo` và `MBeanAttributeInfo`. Một getter như `int getPendingCount()` của Standard MBean sẽ tạo attribute `PendingCount`, thường trả về `Integer` khi gọi `MBeanServerConnection.getAttribute(...)`. Với Spring JMX annotation, getter gắn `@ManagedAttribute` cũng có thể công bố attribute tương ứng.

Không nên đoán kiểu dữ liệu chỉ từ tên attribute. Kiểm tra metadata **và giá trị thực tế**:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

// server là MBeanServerConnection đã được cấu hình từ trước.
ObjectName name = new ObjectName(
    "demo.integration:type=Queue,name=Orders");

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf("%s : %s, readable=%s%n",
        attribute.getName(), attribute.getType(), attribute.isReadable());
}

Object value = server.getAttribute(name, "PendingCountText");
System.out.println(value == null ? "null" : value.getClass().getName());
```

| Attribute khai báo | Kiểu có thể nhận khi `getAttribute` | Xử lý khuyến nghị |
| --- | --- | --- |
| `int PendingCount` | `Integer` | So sánh số trực tiếp hoặc chuẩn hóa sang `long` |
| `long ProcessedTotal` | `Long` | Giữ dạng số nguyên 64-bit |
| `boolean Ready` | `Boolean` | So sánh `payload == true` hoặc xử lý Boolean trực tiếp |
| `String PendingCountText` | `String` | Parse tường minh thành `Long`/`Integer` trước so sánh |
| `double LoadRatio` | `Double` | Xác minh phạm vi, giá trị đặc biệt và đơn vị trước so sánh |
| `CompositeData HeapMemoryUsage` | `CompositeData` | Trích xuất field, kiểm tra `CompositeType` |
| `TabularData` của một bảng quản trị | `TabularData` | Chuyển các hàng/khóa sang DTO hoặc collection rõ ràng |

MBean từ JVM khác có thể dùng **JMX Open Types**. Ví dụ `java.lang:type=Memory` công bố attribute `HeapMemoryUsage` dưới dạng `CompositeData` khi truy cập qua JMX. Tránh ép kiểu thẳng sang `Map<String,Object>` hoặc một POJO nếu chưa có converter tương ứng.

## 4. Ví dụ hoàn chỉnh: biến giá trị JMX dạng chuỗi thành cảnh báo số học

Ta xây dựng một nguồn số liệu có hai managed attribute: `PendingCount` (số nguyên) và `PendingCountText` (chuỗi). Pipeline chọn đọc dạng chuỗi nhằm minh họa chuyển kiểu:

**JMX → `rawPendingCount` → Transformer (String → Long) → Filter (`>= 100`) → Logging adapter**.

### 4.1. Dependency

Với Maven và Spring Integration BOM/Spring Boot đang quản lý phiên bản:

```xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jmx</artifactId>
</dependency>
```

Nếu không có dependency management, khai báo phiên bản tương thích với Spring Integration của dự án. Ví dụ sử dụng Spring Framework JMX exporter và XML namespace của Spring Integration.

### 4.2. MBean giả lập số message đang chờ

File `src/main/java/demo/jmx/OrdersQueueMetrics.java`:

```java
package demo.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName = "demo.integration:type=Queue,name=Orders")
public class OrdersQueueMetrics {
    private final AtomicInteger pending = new AtomicInteger(125);

    @ManagedAttribute(description = "Số message còn chờ")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedAttribute(description = "Số message còn chờ biểu diễn bằng chuỗi")
    public String getPendingCountText() {
        return Integer.toString(pending.get());
    }

    @ManagedAttribute(description = "Hàng đợi sẵn sàng nhận message")
    public boolean isReady() {
        return pending.get() < 500;
    }
}
```

Các getter trên công bố ba attribute `PendingCount`, `PendingCountText` và `Ready`. Giá trị khởi tạo 125 nhằm tạo ra một cảnh báo kiểm thử ngay lần poll đầu tiên. Trong ứng dụng thực, getter nên đọc metric hiện hành từ queue/client tương ứng; tên attribute không có quan hệ tự động với Kafka topic hay JMS destination.

### 4.3. Cấu hình XML cho luồng đọc, chuyển kiểu và kiểm tra ngưỡng

File `src/main/resources/jmx-attribute-expression.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-jmx="http://www.springframework.org/schema/integration/jmx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/jmx
           https://www.springframework.org/schema/integration/jmx/spring-integration-jmx.xsd">

    <context:mbean-server/>
    <context:mbean-export server="mbeanServer"/>
    <bean id="ordersQueueMetrics" class="demo.jmx.OrdersQueueMetrics"/>

    <int:channel id="rawPendingCount"/>
    <int:channel id="numericPendingCount"/>
    <int:channel id="criticalPendingCount"/>

    <!-- Giá trị JMX là chuỗi, ví dụ "125". -->
    <int-jmx:attribute-polling-channel-adapter
        id="ordersPendingSource"
        channel="rawPendingCount"
        mbean-server="mbeanServer"
        object-name="demo.integration:type=Queue,name=Orders"
        attribute-name="PendingCountText">
        <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
    </int-jmx:attribute-polling-channel-adapter>

    <!-- Biến String thành Long để so sánh số học. -->
    <int:transformer
        input-channel="rawPendingCount"
        output-channel="numericPendingCount"
        expression="T(java.lang.Long).valueOf(payload.trim())"/>

    <!-- Giá trị nhỏ hơn 100 sẽ bị lọc khỏi nhánh cảnh báo. -->
    <int:filter
        input-channel="numericPendingCount"
        output-channel="criticalPendingCount"
        expression="payload >= 100"/>

    <int:logging-channel-adapter
        channel="criticalPendingCount"
        level="WARN"
        expression="'Orders queue pending: ' + payload"/>
</beans>
```

Tại mỗi lần poll, adapter lấy `PendingCountText` rồi đẩy `"125"` vào `rawPendingCount`. Transformer tạo ra `Long 125`; filter đánh giá `125 >= 100`, do đó chuyển tiếp message đến logging adapter. Nếu nguồn trả về `"42"`, filter sẽ từ chối message, không phát cảnh báo theo cấu hình này. `DirectChannel` được tạo bởi `<int:channel/>` giúp các bước transformer/filter/logging chạy trên luồng xử lý tương ứng của poller.

Để chạy thử, có thể khởi động context:

```java
package demo.jmx;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class RunAttributeFlow {
    public static void main(String[] args) throws Exception {
        try (var context = new ClassPathXmlApplicationContext(
                "jmx-attribute-expression.xml")) {
            // Cho ứng dụng thử nghiệm tồn tại đủ lâu để poller đọc attribute.
            Thread.sleep(12_000L);
        }
    }
}
```

Trong một ứng dụng server thực, lifecycle do Spring Boot hoặc container quản lý, không dùng `Thread.sleep(...)` như một cơ chế điều phối nghiệp vụ. Output kỳ vọng là log WARN với `Orders queue pending: 125` theo chu kỳ poll (phụ thuộc cấu hình logging và lịch chạy).

### 4.4. Nếu attribute đã là số: bỏ bước parse

MBean trên cũng công bố `PendingCount` kiểu `int`. Có thể thay pipeline bằng việc cho adapter đọc trực tiếp `attribute-name="PendingCount"`, trả `Integer`, rồi nối vào filter so sánh số:

```xml
<!-- Đây là cấu hình thay thế, không khai báo song song với adapter cùng id. -->
<int-jmx:attribute-polling-channel-adapter
    id="ordersPendingSource"
    channel="numericPendingCount"
    object-name="demo.integration:type=Queue,name=Orders"
    attribute-name="PendingCount">
    <int:poller fixed-delay="5000" max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
```

Với biến thể này, **bỏ transformer** đang nhận `rawPendingCount`, giữ filter và logging adapter. `Integer` là kiểu số nên SpEL có thể thực hiện phép so sánh với literal `100`. Nếu downstream yêu cầu duy nhất kiểu `Long`, có thể chuẩn hóa rõ ràng bằng `payload.longValue()` trong một transformer, nhưng không cần chuyển mọi giá trị số thành chuỗi rồi parse lại.

## 5. Hiểu ngữ cảnh đánh giá SpEL trong Spring Integration

SpEL là ngôn ngữ biểu thức của Spring dùng ở transformer, filter, router và nhiều endpoint khác. Một số ví dụ khi payload là giá trị được đọc từ JMX:

| Payload đầu vào | Expression ở endpoint xử lý message | Ý nghĩa và kết quả |
| --- | --- | --- |
| `Integer 125` | `payload >= 100` | `true` |
| `Long 42` | `payload >= 100` | `false` |
| `String "125"` | `T(java.lang.Long).valueOf(payload.trim())` | Tạo `Long 125` |
| `Boolean true` | `payload == true` | `true` |
| `String "WARM"` | `payload.equalsIgnoreCase('WARM')` | `true` |
| `CompositeData` chứa key `used` | `payload.get('used')` | Trả giá trị của trường `used`, cần kiểm tra kiểu |

### 5.1. `expression`, `${...}` và `#{...}` có mục đích khác nhau

- `attribute-name="PendingCountText"` là **tên attribute JMX**, được cấu hình cho source.
- `attribute-name="${jmx.queue.attribute}"` là **property placeholder**, được resolve khi tạo Spring context nếu ứng dụng đã nạp properties tương ứng. Nó hữu ích để chọn tên theo môi trường, không tự biến attribute thành lựa chọn động mỗi message.
- `object-name="#{@jmxTargetName}"` là một ví dụ dùng **Spring bean expression** để lấy cấu hình khi tạo bean (giả sử `jmxTargetName` là bean phù hợp). Không nên coi đây là expression chạy lại với payload sau mỗi lần poll.
- `expression="payload >= 100"` trên `<int:filter>` là **SpEL xử lý từng message** sau khi adapter đã đọc giá trị JMX.

Đối với một inbound poller, thời điểm lấy dữ liệu chưa có request message từ upstream, nên không thể mặc định sử dụng `headers.customerId` hay `payload.queueName` để chọn attribute JMX giống như khi xử lý một message đã tồn tại. Nếu cần đọc attribute khác nhau theo từng request, hãy xây dựng luồng request/reply hoặc `MessageSource` có hợp đồng chọn đích rõ ràng thay vì giả định `attribute-name` nhận payload của request.

### 5.2. Ngưỡng cấu hình thay vì ngưỡng hard-code

Có thể để một bean cung cấp ngưỡng kiểm soát:

```java
package demo.jmx;

public class QueueThresholds {
    public long getCriticalPendingCount() {
        return 100L;
    }
}
```

Với bean `<bean id="queueThresholds" class="demo.jmx.QueueThresholds"/>`, filter có thể dùng:

```xml
<int:filter
    input-channel="numericPendingCount"
    output-channel="criticalPendingCount"
    expression="payload >= @queueThresholds.criticalPendingCount"/>
```

SpEL `@queueThresholds` truy cập bean được phép trong evaluation context, còn `criticalPendingCount` đọc thuộc tính JavaBean (`getCriticalPendingCount()`). Với ngưỡng thay đổi theo thời gian, cần cân nhắc cache, thread-safety và kiểm thử rằng giá trị mới thực sự được đọc theo thiết kế. Đừng đưa dữ liệu không tin cậy trực tiếp vào biểu thức SpEL có quyền truy cập bean hoặc class Java.

## 6. Type conversion: từ JMX sang payload nghiệp vụ

**Type conversion** nên được đặt ở ranh giới ngay sau nguồn JMX, trước khi filter/router xử lý. Đây là nơi chuẩn hóa kiểu, đơn vị và cấu trúc để downstream không phải đoán giá trị.

### 6.1. Chuyển đổi tường minh bằng SpEL

```xml
<!-- String "125" -> Long 125 -->
<int:transformer input-channel="rawPendingCount"
                 output-channel="numericPendingCount"
                 expression="T(java.lang.Long).valueOf(payload.trim())"/>
```

Khi giá trị trả về đã là `Number`, transformer có thể dùng `payload.longValue()` để chuẩn hóa từ `Integer` sang `Long`. Cần kiểm tra nguy cơ tràn số, làm tròn và độ chính xác khi chuyển từ `Double` hoặc `BigDecimal` sang số nguyên.

### 6.2. Chuyển đổi bằng Spring `ConversionService`

Với nhiều nguồn JMX, nên tập trung quy tắc chuyển kiểu vào một thành phần Java có thể tái sử dụng:

```java
package demo.jmx;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public final class PendingCountNormalizer {
    private final ConversionService conversions = new DefaultConversionService();

    public Long normalize(Object raw) {
        if (raw == null) {
            throw new IllegalArgumentException("JMX PendingCount is null");
        }

        Long result = conversions.convert(raw, Long.class);
        if (result == null || result < 0) {
            throw new IllegalArgumentException(
                "Invalid pending count from JMX: " + raw);
        }
        return result;
    }
}
```

Gắn vào Spring Integration transformer:

```xml
<bean id="pendingCountNormalizer"
      class="demo.jmx.PendingCountNormalizer"/>

<int:transformer input-channel="rawPendingCount"
                 output-channel="numericPendingCount"
                 ref="pendingCountNormalizer"
                 method="normalize"/>
```

Đây là **cấu hình thay thế** cho transformer SpEL có cùng `input-channel`/`output-channel`, không nên khai báo cả hai cùng tiêu thụ một `DirectChannel`. `DefaultConversionService` hỗ trợ các chuyển đổi phổ biến như `String` → `Long`; với DTO, enum hoặc định dạng đặc biệt, cần đăng ký `Converter` tùy chỉnh hoặc viết logic parse và validation cụ thể.

**Phân biệt quan trọng:** `ConversionService` chuyển đổi kiểu của giá trị Java. Nó không tự biết một metric là *milliseconds* hay *seconds*, không tự xác định timezone, cũng không tự bảo đảm số đo có ý nghĩa nghiệp vụ. Khi dữ liệu có đơn vị, nên ghi rõ schema, ví dụ `latencyMillis` và dùng `Duration.ofMillis(value)` ở tầng chuẩn hóa.

### 6.3. JMX Open Types: `CompositeData` và `TabularData`

Đối với metric phức tạp, JMX có thể trả về `CompositeData` thay vì `Map`. Ví dụ truy cập `HeapMemoryUsage` của JVM:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName memory = new ObjectName("java.lang:type=Memory");
CompositeData usage = (CompositeData) server.getAttribute(
    memory, "HeapMemoryUsage");

long usedBytes = ((Number) usage.get("used")).longValue();
long maxBytes = ((Number) usage.get("max")).longValue();
System.out.println("Heap used bytes = " + usedBytes);
```

Nếu đọc `HeapMemoryUsage` bằng JMX polling adapter, payload thường là `CompositeData`; transformer có thể trích xuất trường `used` bằng `payload.get('used')`. Kiểm tra metadata (`CompositeType`) và xử lý giá trị `max = -1` có thể biểu thị giới hạn tối đa không xác định. Đừng chia cho `maxBytes` khi `maxBytes <= 0`, và đừng giả định `CompositeData` luôn có những key giống nhau giữa các MBean.

Với **tree-polling JMX adapter**, Spring Integration có `MBeanObjectConverter` (ví dụ `DefaultMBeanObjectConverter`) để chuyển cấu trúc cây MBean sang những dạng dữ liệu đơn giản hơn, đồng thời có bộ lọc attribute. Cơ chế converter đó phục vụ **tree-polling** và khác với việc một **attribute-polling adapter** đọc một thuộc tính rồi transformer xử lý payload của nó.

### 6.4. Null, chuỗi rỗng và dữ liệu không hợp lệ

Đừng xem các giá trị sau là tương đương:

| Giá trị JMX | Cách hiểu đúng | Chính sách gợi ý |
| --- | --- | --- |
| `0` | Số đo hợp lệ bằng không | Giữ và xử lý bình thường |
| `"0"` | Chuỗi biểu diễn số không | Parse nếu contract cho phép |
| `""` hoặc chuỗi toàn khoảng trắng | Giá trị không có dữ liệu số | Đánh dấu invalid; cảnh báo hoặc chuyển đến error flow |
| `null` | Không có giá trị attribute | Có thể không tạo message từ polling source; cần giám sát số lần poll thành công |
| `"N/A"` | Marker nghiệp vụ | Xây quy tắc rõ, không ép thành 0 |
| Số âm ngoài miền hợp lệ | Số đo không hợp lệ hoặc sentinel | Kiểm tra contract trước khi phát alert |

Một transformer SpEL `Long.valueOf(...)` sẽ thất bại nếu nhận `"N/A"` hay `""`; lỗi parse cần được quan sát qua lỗi của poller và flow. Nếu muốn gửi giá trị lỗi thành một message có cấu trúc riêng, hãy dùng transformer Java trả về một DTO trạng thái (ví dụ `MetricReading(valid, value, reason)`) thay vì âm thầm gán số 0. Với dữ liệu đo thường xuyên, quyết định có **giữ giá trị trước đó**, **phát cảnh báo thiếu số liệu**, hay **dừng xử lý** phải được nêu rõ.

## 7. Những lỗi hay gặp trong biểu thức và chuyển kiểu

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Adapter khởi động lỗi vì không tìm thấy attribute | Sai `attribute-name`, `ObjectName`, MBean chưa đăng ký hoặc server khác | Kiểm tra `MBeanInfo.getAttributes()`, tên chính xác và `mbeanServer` |
| `AttributeNotFoundException` | Getter không được công bố hoặc sai chữ hoa/thường | Kiểm tra `PendingCount` khác `pendingCount`; với `getX()` tên JMX thường là `X` |
| SpEL lỗi khi gọi `.trim()` | Payload không phải `String`, hoặc `null` | Quan sát kiểu thực bằng JMX; chuẩn hóa theo `instanceof`/converter |
| `NumberFormatException` | Chuỗi số không hợp lệ, có dấu phân cách hoặc đơn vị | Chuẩn hóa và validate trước khi parse; quy định format rõ |
| Filter so sánh sai | Đang so sánh chuỗi, hoặc ngưỡng không đúng kiểu/đơn vị | Chuyển thành `Number`, chuẩn hóa đơn vị trước so sánh |
| `ClassCastException` với Open Types | Ép `CompositeData` thành `Map`/DTO trực tiếp | Trích xuất `CompositeData.get(key)` hoặc viết converter riêng |
| Không có message sau một lần poll | Attribute `null`, nguồn lỗi hoặc không lấy được giá trị | Giám sát log/error channel/metrics của poller; phân biệt 0 và không có dữ liệu |
| Poller dồn việc hoặc chậm | MBean call JMX remote chậm, transformer xử lý lâu | Cấu hình polling hợp lý, timeout kết nối và chiến lược xử lý lỗi |
| Giá trị số bị mất độ chính xác | Ép `double`/`BigDecimal` xuống số nguyên hoặc dùng sai đơn vị | Chọn kiểu phù hợp, giữ precision, đo thử giới hạn |

### Lưu ý về poller và xử lý lỗi

JMX attribute-polling adapter là **inbound, theo lịch poller**. Mỗi lần poll nó gọi JMX và có thể tạo message nếu có giá trị. Với `fixed-delay="5000"`, khoảng nghỉ được tính theo **fixed delay** sau lần chạy trước; không phải cam kết rằng metric luôn được đọc chính xác mỗi 5 giây. Nếu xử lý hoặc kết nối JMX mất thời gian, chu kỳ thực tế dài hơn.

Với `DirectChannel`, transformer và filter thường xử lý đồng bộ trong luồng poller. Nếu một phép chuyển kiểu ném ngoại lệ, cần theo dõi lỗi poller/error channel; không giả định message lỗi đã tới destination. Khi chuyển sang kênh bất đồng bộ, thiết kế error flow và retry riêng, tránh làm mất tín hiệu lỗi parse. Những operation JMX có tác dụng phụ phải được quản lý retry khác với việc chỉ đọc attribute.

## 8. Bài thực hành và checklist xác minh

### Thực hành

1. Khởi động `RunAttributeFlow`, kiểm tra MBean `demo.integration:type=Queue,name=Orders` xuất hiện trong JConsole/VisualVM và có attribute `PendingCountText`.
2. Đọc trực tiếp bằng `MBeanServerConnection.getAttribute(...)` để xác định giá trị `"125"` và kiểu `String` trước khi đưa vào message.
3. Theo dõi log WARN; kiểm tra transformer trả `Long 125`, filter `payload >= 100` cho phép đi qua.
4. Đổi giá trị `pending` của demo thành 42, xác nhận filter không còn đẩy message vào nhánh cảnh báo.
5. Thay `attribute-name="PendingCountText"` thành `PendingCount`, bỏ transformer parse chuỗi và dùng filter trực tiếp với số nguyên.
6. Thử một chuỗi dữ liệu không hợp lệ như `"N/A"` ở một MBean thử nghiệm; quan sát lỗi parse và thiết kế đường xử lý phù hợp.
7. Đọc `java.lang:type=Memory`/`HeapMemoryUsage`, trích `used` và `max`, kiểm tra cả trường hợp `max <= 0`.

### Câu hỏi tự kiểm tra

1. Tại sao `attribute-name="PendingCountText"` khác về bản chất với `expression="payload >= 100"`?
2. Khi nào `${...}` được resolve, và khi nào SpEL ở transformer được đánh giá?
3. Nếu MBean công bố `int getPendingCount()`, vì sao không nhất thiết phải parse giá trị nhận được thành `Long`?
4. Vì sao `"125"` không nên được so sánh trực tiếp như số nguyên trong filter?
5. `CompositeData` khác `Map` như thế nào, và cách nào an toàn để lấy field `used`?
6. Nếu attribute JMX trả `null` hoặc `"N/A"`, hệ thống giám sát nên phân biệt những trạng thái đó với số 0 ra sao?
7. `DefaultMBeanObjectConverter` của tree-polling khác gì với `ConversionService` dùng ở transformer?

## Tài liệu tham khảo

- [Spring Integration Reference — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): attribute-polling adapter, tên attribute/MBean, poller và converter của tree-polling.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transformer và biểu thức SpEL cho payload.
- [Spring Integration Reference — Filter](https://docs.spring.io/spring-integration/reference/filter.html): điều kiện xử lý message bằng SpEL và xử lý message bị từ chối.
- [Spring Framework Reference — JMX Exporting](https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html): `@ManagedAttribute`, `MBeanExporter` và thuộc tính được công bố.
- [Spring Framework Reference — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService` và converter tùy chỉnh.
- [Java SE API — `MBeanServerConnection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): truy vấn metadata và đọc attribute.
- [Java SE API — `CompositeData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html): biểu diễn attribute phức tạp trong JMX Open Types.
