# Open MBean và các kiểu dữ liệu mở rộng chuẩn

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao JMX cung cấp **Open MBean** và mô hình **OpenType** nhằm trao đổi dữ liệu quản trị theo cấu trúc dễ hiểu đối với công cụ JMX, không đòi client biết class nghiệp vụ tùy chỉnh.
- Phân biệt **Standard MBean**, **MXBean**, **DynamicMBean** và **Open MBean** về hợp đồng quản trị và cách mô tả dữ liệu.
- Nhận diện các kiểu chuẩn \`SimpleType\`, \`ArrayType\`, \`CompositeType\` và \`TabularType\`; hiểu dữ liệu tương ứng \`CompositeData\` và \`TabularData\`.
- Tạo \`CompositeDataSupport\` và \`TabularDataSupport\`, mô tả schema bằng \`OpenMBeanAttributeInfoSupport\`, \`OpenMBeanOperationInfoSupport\` và công bố một Open MBean qua \`MBeanServer\`.
- Biết cách xử lý giá trị phức tạp, tính ổn định của schema, khả năng tương thích client và các giới hạn khi tích hợp với Spring Framework.

## 2. Bối cảnh: vấn đề Open MBean giải quyết

JMX cho phép công cụ như JConsole và client tự viết quan sát hoặc thao tác với những MBean đã đăng ký trong \`MBeanServer\`. Với Java object bình thường, kiểu trả về có thể là class ứng dụng, ví dụ:

\`\`\`java
public final class QueueSnapshot {
    private final long pending;
    private final long processed;
    // Các field và API riêng của ứng dụng...
}
\`\`\`

Nếu công bố trực tiếp một kiểu tùy chỉnh, client từ xa có thể cần class đó trong classpath và phải hiểu cách giải mã nó. Việc này gây khó khăn khi công cụ quản trị độc lập với ứng dụng hoặc phiên bản class thay đổi.

**Open MBean** dùng bộ kiểu dữ liệu chuẩn, được mô tả bằng metadata có thể khám phá qua JMX. Thay vì yêu cầu client biết \`QueueSnapshot\`, server có thể trả về một \`CompositeData\` có schema gồm \`pending: Long\` và \`processed: Long\`. Client chỉ cần JMX API chuẩn để đọc các key và giá trị.

\`\`\`text
Trạng thái nội bộ
QueueSnapshot(pending=12, processed=840)
              |
              | chuyển thành open data
              v
CompositeType "QueueSnapshot"
  pending   -> SimpleType.LONG
  processed -> SimpleType.LONG
              |
              v
CompositeData
  {pending=12, processed=840}
              |
              v
MBeanServer -> JMX client
              |
              v
Client đọc metadata + key/value
không cần class QueueSnapshot
\`\`\`

Từ “open” ở đây có nghĩa kiểu dữ liệu và cấu trúc có thể được công cụ quản trị khám phá và hiểu theo hợp đồng JMX. Nó **không có nghĩa mở truy cập công khai, bỏ xác thực hoặc cho phép gọi mọi method**.

## 3. Các lớp và giao diện nền tảng

Các thành phần Open MBean nằm chủ yếu trong package \`javax.management.openmbean\`.

| Thành phần | Chức năng |
| --- | --- |
| \`OpenType<T>\` | Mô tả một kiểu dữ liệu được JMX công nhận trong mô hình open data. |
| \`SimpleType<T>\` | Kiểu vô hướng chuẩn, ví dụ \`STRING\`, \`INTEGER\`, \`LONG\`, \`BOOLEAN\`, \`DATE\`, \`OBJECTNAME\`. |
| \`ArrayType<T>\` | Kiểu mảng của một OpenType hợp lệ. |
| \`CompositeType\` | Schema bản ghi có các trường được đặt tên và kiểu tương ứng. |
| \`CompositeData\` | Giá trị bản ghi tuân theo \`CompositeType\`. |
| \`CompositeDataSupport\` | Lớp triển khai phổ biến của \`CompositeData\`. |
| \`TabularType\` | Schema tập hợp các hàng dạng \`CompositeData\` có khóa chỉ mục. |
| \`TabularData\` | Giá trị dạng bảng theo \`TabularType\`. |
| \`TabularDataSupport\` | Lớp triển khai phổ biến của \`TabularData\`. |
| \`OpenMBeanInfoSupport\` | Metadata của Open MBean: tên class, mô tả, thuộc tính, constructor, operation, notification. |
| \`OpenMBeanAttributeInfoSupport\` | Metadata một thuộc tính, bao gồm OpenType, khả năng đọc/ghi và ràng buộc tùy chọn. |
| \`OpenMBeanOperationInfoSupport\` | Metadata một operation, bao gồm kiểu trả về và tham số. |
| \`OpenMBeanParameterInfoSupport\` | Metadata một tham số operation hoặc constructor. |

Lưu ý sự khác nhau giữa **mô tả kiểu** và **giá trị**:

\`\`\`text
CompositeType   = cấu trúc: field nào, kiểu gì?
CompositeData   = giá trị cụ thể theo cấu trúc đó.

TabularType     = cấu trúc của các hàng + cột chỉ mục.
TabularData     = tập hợp các hàng thực tế.

OpenMBeanInfo   = mô tả bề mặt quản trị của MBean.
MBeanServer     = nơi tiếp nhận và thực thi yêu cầu dựa trên bề mặt đó.
\`\`\`

## 4. SimpleType: các giá trị vô hướng tiêu chuẩn

\`SimpleType\` mô tả những kiểu Java chuẩn JMX cho phép trong open data. Các constant thường gặp:

| Constant | Kiểu Java tương ứng | Ứng dụng |
| --- | --- | --- |
| \`SimpleType.STRING\` | \`String\` | Tên, trạng thái, mô tả ngắn. |
| \`SimpleType.BOOLEAN\` | \`Boolean\` | Bật/tắt tính năng. |
| \`SimpleType.INTEGER\` | \`Integer\` | Số lượng nhỏ, limit, ngưỡng. |
| \`SimpleType.LONG\` | \`Long\` | Bộ đếm, kích thước hoặc thời gian. |
| \`SimpleType.DOUBLE\` | \`Double\` | Tỷ lệ, giá trị đo. |
| \`SimpleType.BIGDECIMAL\` | \`BigDecimal\` | Số thập phân cần độ chính xác. |
| \`SimpleType.BIGINTEGER\` | \`BigInteger\` | Số nguyên lớn. |
| \`SimpleType.DATE\` | \`Date\` | Thời điểm. |
| \`SimpleType.OBJECTNAME\` | \`ObjectName\` | Tham chiếu tên MBean. |
| \`SimpleType.VOID\` | \`Void\` | Kiểu trả về \`void\` của operation. |

Các kiểu số nguyên nhỏ như \`BYTE\` và \`SHORT\`, kiểu \`FLOAT\`, \`CHARACTER\` cũng được hỗ trợ. Dù ứng dụng có enum hoặc class tự định nghĩa, \`SimpleType\` không tự chấp nhận kiểu đó chỉ vì nó implement \`Serializable\`. Cần biểu diễn bằng một OpenType phù hợp, chẳng hạn enum thành \`String\`.

Một số kiểu có thể có \`null\` ở vị trí giá trị theo quy tắc của dữ liệu chứa chúng, nhưng phải thiết kế rõ ý nghĩa \`null\`; không coi \`null\` như một \`SimpleType\` mới.

\`\`\`java
import javax.management.openmbean.SimpleType;

System.out.println(SimpleType.STRING.getClassName());
System.out.println(SimpleType.LONG.getTypeName());
System.out.println(SimpleType.BOOLEAN.isValue(Boolean.TRUE));
System.out.println(SimpleType.LONG.isValue("123")); // false: String không phải Long
\`\`\`

\`isValue\` kiểm tra đối tượng Java có khớp kiểu open data được khai báo hay không. Chuyển đổi \`"123"\` thành \`Long\` là trách nhiệm của code ứng dụng nếu đầu vào là String.

## 5. CompositeType và CompositeData: bản ghi nhiều trường

### 5.1. Khai báo schema

Dữ liệu phức hợp có thể mô tả một snapshot gồm nhiều chỉ số:

\`\`\`java
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

CompositeType queueType = new CompositeType(
    "QueueSnapshot",             // typeName
    "Current queue statistics",  // description
    new String[] { "pending", "processed", "paused" },
    new String[] {
        "Tasks awaiting processing",
        "Tasks already processed",
        "Whether the queue is paused"
    },
    new OpenType<?>[] {
        SimpleType.LONG,
        SimpleType.LONG,
        SimpleType.BOOLEAN
    }
);
\`\`\`

\`CompositeType\` mô tả các item theo tên và kiểu. Mỗi item name phải hợp lệ và duy nhất; các mảng \`itemNames\`, \`itemDescriptions\`, \`itemTypes\` phải tương ứng về độ dài. Constructor ném \`OpenDataException\` nếu schema không hợp lệ.

### 5.2. Tạo giá trị theo schema

\`\`\`java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;

CompositeData snapshot = new CompositeDataSupport(
    queueType,
    new String[] { "pending", "processed", "paused" },
    new Object[] { 12L, 840L, false }
);

System.out.println(snapshot.get("pending")); // 12
System.out.println(snapshot.get("paused"));  // false
System.out.println(snapshot.getCompositeType().getTypeName());
\`\`\`

Có thể dùng constructor dạng \`Map<String, ?>\` để giảm nguy cơ lệch thứ tự dữ liệu:

\`\`\`java
import java.util.Map;

CompositeData snapshot = new CompositeDataSupport(
    queueType,
    Map.of(
        "pending", 12L,
        "processed", 840L,
        "paused", false
    )
);
\`\`\`

Khi dùng \`Map.of\`, không được có key hoặc value \`null\`; nếu cần biểu diễn giá trị \`null\` hợp lệ, dùng cấu trúc \`Map\` phù hợp trước khi tạo \`CompositeDataSupport\`.

Đọc từng trường mà không cần class nghiệp vụ:

\`\`\`java
long pending = (Long) snapshot.get("pending");
boolean paused = (Boolean) snapshot.get("paused");
\`\`\`

Client vẫn cần xử lý trường thiếu và kiểu khác kỳ vọng, nhất là khi có thay đổi schema giữa phiên bản server.

### 5.3. CompositeData không tương đương Java bean

\`CompositeData\` cung cấp giao diện kiểu dictionary có schema cố định. Nó không giữ logic nghiệp vụ, các method service hay graph tham chiếu đối tượng tùy ý. Dữ liệu con phải được biểu diễn bởi những OpenType cho phép, chẳng hạn một \`CompositeType\` lồng nhau, \`ArrayType\` hoặc \`TabularType\`.

Không nên đưa object graph lớn, vòng tham chiếu hoặc dữ liệu nhạy cảm sang JMX chỉ vì \`CompositeData\` có thể chứa nhiều trường.

## 6. ArrayType: danh sách giá trị cùng kiểu

\`ArrayType\` đại diện cho mảng một hoặc nhiều chiều chứa giá trị có OpenType tương ứng:

\`\`\`java
import javax.management.openmbean.ArrayType;
import javax.management.openmbean.SimpleType;

ArrayType<?> tagsType = new ArrayType<>(1, SimpleType.STRING);
ArrayType<?> matrixType = new ArrayType<>(2, SimpleType.INTEGER);
\`\`\`

\`tagsType\` tương ứng với \`String[]\`; \`matrixType\` tương ứng với \`Integer[][]\`. Cần chú ý kiểu primitive array như \`int[]\` có cách khai báo khác biệt so với \`Integer[]\`; API còn có cơ chế \`ArrayType\` cho các primitive array được hỗ trợ. Không tự suy ra \`ArrayType<>(1, SimpleType.INTEGER)\` chấp nhận \`int[]\`.

\`\`\`java
String[] tags = { "critical", "worker" };
System.out.println(tagsType.isValue(tags)); // true
\`\`\`

Một \`CompositeType\` có thể chứa item dạng \`ArrayType\`, ví dụ \`workerNames: String[]\`. Tuy nhiên bảng nhiều hàng có khóa thường được biểu diễn rõ hơn bằng \`TabularType\`.

## 7. TabularType và TabularData: bảng các bản ghi có chỉ mục

### 7.1. Định nghĩa hàng và khóa

Giả sử ta muốn công bố thống kê theo tên queue:

\`\`\`text
name          pending   paused
email         12        false
billing       4         true
search        37        false
\`\`\`

Trước hết định nghĩa schema của một hàng bằng \`CompositeType\`, sau đó định nghĩa schema bảng với khóa \`name\`:

\`\`\`java
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;
import javax.management.openmbean.TabularType;

CompositeType rowType = new CompositeType(
    "QueueRow",
    "A queue status row",
    new String[] { "name", "pending", "paused" },
    new String[] { "Queue name", "Pending tasks", "Paused" },
    new OpenType<?>[] {
        SimpleType.STRING,
        SimpleType.LONG,
        SimpleType.BOOLEAN
    }
);

TabularType tableType = new TabularType(
    "QueueTable",
    "Current queues",
    rowType,
    new String[] { "name" }
);
\`\`\`

\`indexNames\` là danh sách tên các item trong \`rowType\` dùng làm khóa. Trong ví dụ, mỗi \`name\` phải duy nhất trong bảng. Nếu cần khóa kết hợp, dùng nhiều item name, chẳng hạn \`{ "tenant", "name" }\`.

### 7.2. Khởi tạo bảng và thêm hàng

\`\`\`java
import java.util.Map;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.TabularData;
import javax.management.openmbean.TabularDataSupport;

TabularData table = new TabularDataSupport(tableType);

CompositeData email = new CompositeDataSupport(
    rowType,
    Map.of("name", "email", "pending", 12L, "paused", false)
);
CompositeData billing = new CompositeDataSupport(
    rowType,
    Map.of("name", "billing", "pending", 4L, "paused", true)
);

table.put(email);
table.put(billing);

System.out.println(table.size()); // 2

CompositeData selected = table.get(new Object[] { "email" });
System.out.println(selected.get("pending")); // 12
\`\`\`

\`TabularDataSupport\` lưu các \`CompositeData\` đúng schema hàng; mỗi hàng được truy cập theo chỉ mục được định nghĩa bởi \`TabularType\`.

**Phân biệt bảng JMX và database:** \`TabularData\` là cấu trúc biểu diễn và trao đổi dữ liệu quản trị, không phải hệ SQL, không tự có phân trang, transaction hay query optimizer. Tránh trả về bảng quá lớn qua JMX vì chi phí copy, serialize và render trên công cụ quản trị.

### 7.3. Khi nào chọn CompositeData, khi nào chọn TabularData?

| Nhu cầu | Kiểu phù hợp | Ví dụ |
| --- | --- | --- |
| Một snapshot với các trường cố định | \`CompositeData\` | Số request, thời gian xử lý trung bình, trạng thái. |
| Nhiều snapshot có cấu trúc giống nhau và key ổn định | \`TabularData\` | Thống kê theo queue, cache, tenant. |
| Một mảng phần tử đồng nhất | \`ArrayType\` | Danh sách nhãn, top error codes. |
| Một giá trị đơn giản | \`SimpleType\` | \`Long\` bộ đếm, \`Boolean\` bật/tắt. |

## 8. Open MBean khác gì Standard MBean và MXBean?

### 8.1. Standard MBean

Standard MBean thường dùng interface có hậu tố \`MBean\` để công bố thuộc tính và operation:

\`\`\`java
public interface QueueAdminMBean {
    int getPendingCount();
    void reset();
}
\`\`\`

JMX introspection suy ra metadata từ interface Java. Một Standard MBean có thể có một số kiểu dữ liệu hữu ích nhưng tự nó không bắt buộc mọi chữ ký dùng OpenType.

### 8.2. MXBean

MXBean là cơ chế thuận tiện để ánh xạ một số kiểu Java sang **open data** tiêu chuẩn. Ví dụ, \`@MXBean\` hoặc convention tên interface hậu tố \`MXBean\` cho phép JMX map những kiểu đã được mô tả trong quy tắc MXBean, chẳng hạn kiểu record/bean có cấu trúc phù hợp sang \`CompositeData\`.

\`\`\`java
import javax.management.MXBean;

@MXBean
public interface QueueMonitorMXBean {
    long getPending();
    String getStatus();
}
\`\`\`

MXBean hữu ích khi muốn code typed Java thân thiện với người viết server/client mà vẫn có dạng open data ở ranh giới JMX. Không phải mọi object bất kỳ đều có mapping MXBean hợp lệ.

### 8.3. Open MBean dựa trên metadata

Open MBean sử dụng metadata \`OpenMBeanInfo\` và các OpenType để mô tả hợp đồng quản trị. Thường triển khai qua \`DynamicMBean\` với \`OpenMBeanInfoSupport\`, hoặc thông qua framework hỗ trợ tạo metadata thích hợp.

| Tiêu chí | Standard MBean | MXBean | Open MBean được mô tả tường minh |
| --- | --- | --- | --- |
| Điểm xuất phát | Interface Java theo quy ước | Interface Java với MXBean mapping | Metadata JMX với \`OpenType\` |
| Giao diện lập trình | Getter/setter/operation typed | Getter/setter/operation typed và mapping | Có thể xử lý dynamic theo tên và metadata |
| Client hiểu kiểu | Có thể phụ thuộc kiểu tùy chỉnh | Dữ liệu được map sang open data | Dữ liệu được công bố trực tiếp bằng open data |
| Khi phù hợp | Quản trị nội bộ đơn giản | API typed nhưng client độc lập | MBean động, schema cần mô tả rõ hoặc framework JMX |

**Quan hệ quan trọng:** Open MBean là một hợp đồng về metadata và kiểu dữ liệu mở; \`DynamicMBean\` là một giao diện Java cho phép tự hiện thực get/set/invoke/getMBeanInfo. Hai khái niệm có liên quan nhưng không đồng nghĩa. Một \`DynamicMBean\` bất kỳ không nhất thiết công bố OpenType đầy đủ.

## 9. Ví dụ Open MBean hoàn chỉnh bằng DynamicMBean

Ví dụ này trả về một \`CompositeData\` read-only và cung cấp operation \`reset\`. Toàn bộ giao diện quản trị được mô tả tường minh với \`OpenMBeanInfoSupport\`.

### 9.1. Mã nguồn

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.Attribute;
import javax.management.AttributeList;
import javax.management.AttributeNotFoundException;
import javax.management.DynamicMBean;
import javax.management.InvalidAttributeValueException;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanException;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.ReflectionException;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenDataException;
import javax.management.openmbean.OpenMBeanAttributeInfoSupport;
import javax.management.openmbean.OpenMBeanInfoSupport;
import javax.management.openmbean.OpenMBeanOperationInfoSupport;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public final class OpenQueueMonitor implements DynamicMBean {

    private final CompositeType snapshotType;
    private final MBeanInfo mbeanInfo;
    private long pending = 12L;
    private long processed = 840L;

    public OpenQueueMonitor() throws OpenDataException {
        snapshotType = new CompositeType(
            "QueueSnapshot",
            "Snapshot of queue counters",
            new String[] { "pending", "processed" },
            new String[] { "Pending tasks", "Processed tasks" },
            new OpenType<?>[] { SimpleType.LONG, SimpleType.LONG }
        );

        OpenMBeanAttributeInfoSupport snapshotInfo =
            new OpenMBeanAttributeInfoSupport(
                "Snapshot",
                "Current queue counters",
                snapshotType,
                true,   // readable
                false,  // writable
                false   // isIs
            );

        OpenMBeanOperationInfoSupport resetInfo =
            new OpenMBeanOperationInfoSupport(
                "reset",
                "Reset the counters",
                new javax.management.openmbean.OpenMBeanParameterInfo[0],
                SimpleType.VOID,
                MBeanOperationInfo.ACTION
            );

        mbeanInfo = new OpenMBeanInfoSupport(
            getClass().getName(),
            "Queue monitor with open data",
            new javax.management.openmbean.OpenMBeanAttributeInfo[] {
                snapshotInfo
            },
            new javax.management.openmbean.OpenMBeanConstructorInfo[0],
            new javax.management.openmbean.OpenMBeanOperationInfo[] {
                resetInfo
            },
            new MBeanNotificationInfo[0]
        );
    }

    @Override
    public synchronized Object getAttribute(String attribute)
            throws AttributeNotFoundException, MBeanException,
                   ReflectionException {
        if ("Snapshot".equals(attribute)) {
            try {
                return new CompositeDataSupport(
                    snapshotType,
                    Map.of("pending", pending, "processed", processed)
                );
            } catch (OpenDataException e) {
                throw new MBeanException(e, "Invalid queue snapshot");
            }
        }
        throw new AttributeNotFoundException(attribute);
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException, MBeanException,
                   ReflectionException {
        throw new AttributeNotFoundException(
            attribute == null ? "null" : attribute.getName()
        );
    }

    @Override
    public AttributeList getAttributes(String[] attributes) {
        AttributeList values = new AttributeList();
        if (attributes != null) {
            for (String attribute : attributes) {
                try {
                    values.add(new Attribute(
                        attribute,
                        getAttribute(attribute)
                    ));
                } catch (Exception ignored) {
                    // Không thêm những thuộc tính không đọc được.
                }
            }
        }
        return values;
    }

    @Override
    public AttributeList setAttributes(AttributeList attributes) {
        // MBean mẫu không có thuộc tính ghi được.
        return new AttributeList();
    }

    @Override
    public synchronized Object invoke(
            String actionName,
            Object[] params,
            String[] signature)
            throws MBeanException, ReflectionException {
        if ("reset".equals(actionName)
                && (params == null || params.length == 0)
                && (signature == null || signature.length == 0)) {
            pending = 0L;
            processed = 0L;
            return null;
        }
        throw new ReflectionException(
            new NoSuchMethodException(actionName)
        );
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        return mbeanInfo;
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=QueueMonitor,name=Orders"
        );
        server.registerMBean(new OpenQueueMonitor(), name);
        try {
            CompositeData before = (CompositeData)
                server.getAttribute(name, "Snapshot");

            System.out.println(before.get("pending"));   // 12
            System.out.println(before.get("processed")); // 840

            server.invoke(
                name, "reset", new Object[0], new String[0]
            );

            CompositeData after = (CompositeData)
                server.getAttribute(name, "Snapshot");
            System.out.println(after.get("pending"));    // 0
            System.out.println(after.get("processed"));  // 0
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

### 9.2. Giải thích luồng hoạt động

1. Constructor tạo \`CompositeType\` làm schema cho thuộc tính \`Snapshot\`.
2. \`OpenMBeanAttributeInfoSupport\` công bố thuộc tính kiểu \`CompositeType\`, được đọc nhưng không ghi.
3. \`OpenMBeanOperationInfoSupport\` mô tả operation \`reset\` trả về \`void\` qua \`SimpleType.VOID\`.
4. \`OpenMBeanInfoSupport\` ghép metadata thành giao diện quản trị để \`MBeanServer\` và client khám phá.
5. Client gọi \`server.getAttribute(name, "Snapshot")\`; \`getAttribute\` trả về \`CompositeDataSupport\` chứa các bộ đếm.
6. Client gọi \`invoke(..., "reset", ...)\`; bộ đếm đặt lại và lần đọc tiếp theo trả về giá trị mới.
7. \`finally\` đảm bảo MBean được hủy đăng ký sau ví dụ.

Đối với dự án thật, việc nuốt lỗi của từng thuộc tính trong \`getAttributes\` nên có chiến lược ghi nhận phù hợp với đặc tả và hoạt động quan sát; ví dụ trên chỉ giữ hành vi trả danh sách thuộc tính đọc được. Nếu một getter tốn tài nguyên hoặc có side effect, cần thiết kế lại chính getter đó.

### 9.3. Khám phá metadata từ client

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName()
        + " : " + attribute.getType()
        + " (readable=" + attribute.isReadable() + ")"
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Metadata của một Open MBean sẽ dùng những lớp info tương ứng; client có thể kiểm tra \`instanceof OpenMBeanAttributeInfo\` để lấy \`getOpenType()\`:

\`\`\`java
import javax.management.openmbean.OpenMBeanAttributeInfo;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    if (attribute instanceof OpenMBeanAttributeInfo open) {
        System.out.println(open.getOpenType());
    }
}
\`\`\`

\`MBeanInfo\` hiển thị class name mô tả kiểu Java/JMX, còn \`OpenMBeanAttributeInfo.getOpenType()\` cung cấp schema chi tiết cần thiết để diễn giải giá trị lồng nhau.

## 10. Giá trị kiểu phức tạp, nullable và lỗi schema

### 10.1. Kiểm tra tương thích kiểu trước khi tạo dữ liệu

\`CompositeDataSupport\` và \`TabularDataSupport\` thực hiện kiểm tra giá trị theo schema. Ví dụ:

\`\`\`java
CompositeType type = new CompositeType(
    "Counter", "One counter",
    new String[] { "count" },
    new String[] { "Current count" },
    new OpenType<?>[] { SimpleType.LONG }
);

// Hợp lệ:
CompositeData valid = new CompositeDataSupport(
    type, Map.of("count", 12L)
);

// Sai kiểu: Integer thay vì Long, nên lỗi OpenDataException.
CompositeData invalid = new CompositeDataSupport(
    type, Map.of("count", 12)
);
\`\`\`

Cách xử lý đúng là ánh xạ kiểu rõ ràng, ví dụ \`Long.valueOf(sourceValue)\`, và đảm bảo dữ liệu không vượt phạm vi biểu diễn. Không nên tự ý đưa String vào field khai báo LONG để “tránh lỗi”, vì phá hợp đồng với client.

### 10.2. Null và thuộc tính không tồn tại

Đối với \`CompositeData\`, một trường có thể có giá trị \`null\` theo quy tắc của implementation/API, nhưng schema vẫn phải chứa **đúng tên trường**. Giá trị \`null\` không đồng nghĩa “không có field”. Một số cấu trúc bất biến như \`Map.of\` cấm \`null\` ngay từ bước tạo map; đây là ràng buộc của Java Collections, khác với quy tắc open data.

Nên phân biệt:

- **Field không được định nghĩa trong CompositeType**: client phải coi đây là schema khác hoặc yêu cầu sai.
- **Field có mặt nhưng giá trị null**: thuộc tính chưa có giá trị hoặc không áp dụng, theo hợp đồng được công bố.
- **Field có kiểu khác**: dữ liệu sai schema và cần từ chối hoặc chuyển đổi rõ ràng.

### 10.3. Dữ liệu phân tầng

Một \`CompositeType\` có thể chứa item là \`CompositeType\` khác hoặc \`TabularType\`. Ví dụ mô tả một service với \`status: String\` và \`queues: TabularData\`. Mỗi cấp nên giữ tên và kiểu ổn định, tránh phình dữ liệu gây khó đọc trên JConsole.

Nếu cần danh sách phân trang, truy vấn phức tạp hoặc dữ liệu lớn, JMX không phải API dữ liệu phân trang mặc định. Có thể chỉ công bố các số liệu tổng hợp và đường dẫn tới giao diện vận hành chuyên dụng.

## 11. Open MBean, remote JMX và tính tương thích

### 11.1. Client từ xa không cần class nghiệp vụ

Khi client sử dụng \`JMXConnector\` để lấy \`MBeanServerConnection\`, nó có thể gọi:

\`\`\`java
CompositeData snapshot = (CompositeData)
    connection.getAttribute(objectName, "Snapshot");

long pending = (Long) snapshot.get("pending");
\`\`\`

Client sử dụng kiểu dữ liệu thuộc JMX API chuẩn và schema được trả về. Dù vậy, truy cập từ xa vẫn cần connector, cấu hình mạng, xác thực, quyền và cơ chế bảo vệ phù hợp.

### 11.2. Tương thích khi schema thay đổi

Giả sử phiên bản 1 trả \`{pending: Long, processed: Long}\`, phiên bản 2 thêm \`paused: Boolean\`. Client nên đọc schema và chỉ dùng trường cần thiết, đồng thời có chính sách xử lý trường bổ sung. Mặt khác, client ép kiểu và truy cập field trực tiếp có thể hỏng nếu đổi tên \`pending\`, đổi \`Long\` sang \`String\` hoặc bỏ một item.

Khuyến nghị thiết kế:

1. Chọn tên thuộc tính, item và kiểu dữ liệu rõ ràng ngay từ đầu.
2. Giữ ổn định các field cốt lõi, tránh đổi ngữ nghĩa của field đang dùng.
3. Nếu thay đổi không tương thích, công bố schema hoặc \`ObjectName\` mới có version rõ ràng khi cần.
4. Đọc \`OpenType\`/metadata để kiểm tra schema, đặc biệt trước khi ghi thuộc tính hoặc gọi operation.
5. Kiểm tra công cụ quan sát thực tế vì mỗi client có cách trình bày \`CompositeData\` và \`TabularData\` khác nhau.

Không nên giả định mọi loại client sẽ tự động chấp nhận bất kỳ thay đổi schema nào chỉ vì dữ liệu là “open”.

## 12. Open MBean trong hệ sinh thái Spring Framework

Spring Framework cung cấp cơ chế JMX như \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` giúp công bố bean ứng dụng. Trong nhiều tình huống, sử dụng Spring exporter hoặc MXBean giúp giảm lượng mã tự viết.

Tuy nhiên:

- Spring bean và Open MBean là hai mô hình khác nhau. Một bean trong \`ApplicationContext\` không tự động trở thành Open MBean.
- Spring exporter quản lý việc đăng ký MBean và chuyển từ Spring bean sang metadata thích hợp theo cấu hình; nó không mặc định làm mọi kiểu object nghiệp vụ thành \`CompositeData\` hợp lệ.
- Khi muốn công bố dữ liệu có schema chuẩn rõ ràng, có thể đăng ký một \`DynamicMBean\` công bố \`OpenMBeanInfoSupport\`, hoặc chọn MXBean nếu hợp đồng Java phù hợp cơ chế ánh xạ.
- Chỉ một chủ thể nên quản lý đăng ký cho một \`ObjectName\` trong mỗi \`MBeanServer\`, tránh xung đột giữa đăng ký thủ công và \`MBeanExporter\`.

Ví dụ tổ chức thành phần:

\`\`\`text
Spring service / repository
         |
         | cung cấp snapshot nghiệp vụ
         v
OpenQueueMonitor (JMX adapter)
         |
         | CompositeData / OpenMBeanInfo
         v
MBeanServer (platform hoặc server đã cấu hình)
         |
         v
JConsole / JMX client / collector
\`\`\`

Cách tổ chức này giữ logic nghiệp vụ trong service, logic ánh xạ kiểu trong adapter JMX và trách nhiệm registry trong MBeanServer. Việc tách lớp giúp kiểm soát nội dung được phép công bố.

## 13. Bảo mật, hiệu năng và vận hành

**Bảo mật.** Open data không tự bảo vệ thông tin. Nếu một \`CompositeData\` chứa token, mật khẩu, email người dùng hoặc cấu hình bí mật, chúng có thể bị đọc qua JMX khi truy cập được cấp quyền. Chỉ xuất trường có mục đích vận hành, và áp dụng kiểm soát remote JMX nghiêm ngặt.

**Hiệu năng.** Một \`TabularData\` lớn có thể tốn CPU và bộ nhớ để xây dựng, serialize rồi render. Getter JMX thường được polling định kỳ; tránh quét toàn bộ database, khóa tài nguyên lâu hoặc thực thi nghiệp vụ nặng trong \`getAttribute\`.

**Tính nhất quán.** Khi snapshot được lấy từ nhiều bộ đếm đang thay đổi, dữ liệu có thể không cùng một thời điểm nếu không có cơ chế đồng bộ. Hãy xác định yêu cầu consistency: snapshot khóa ngắn, atomic counters hoặc eventual consistency được ghi rõ.

**Quyền điều khiển.** Những operation như \`reset\`, \`clearCache\`, \`pauseWorker\` có tác động thật. Công bố càng ít operation thay đổi trạng thái càng tốt, làm rõ quyền và log vận hành cần thiết.

**Vòng đời.** Đăng ký bằng \`MBeanServer.registerMBean\` phải có đường hủy \`unregisterMBean\` khi kết thúc. Một MBean chỉ nên có ownership rõ ràng để tránh \`InstanceAlreadyExistsException\` lúc khởi động lại context.

**Độ ổn định.** Không đưa giá trị động thành tên item \`CompositeType\` nếu có thể biểu diễn bằng hàng \`TabularData\` với cột khóa; schema thay đổi theo dữ liệu khiến client khó xử lý.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Open MBean cho phép public truy cập JMX.” | “Open” nói về kiểu dữ liệu và metadata; bảo mật kết nối là vấn đề độc lập. |
| “CompositeData là Java Map tùy ý.” | \`CompositeData\` tuân thủ schema \`CompositeType\` với tên và OpenType xác định. |
| “TabularData là SQL table.” | Đây là bảng dữ liệu JMX trong bộ nhớ, tra theo khóa chỉ mục được mô tả, không có SQL engine. |
| “Mọi Serializable class là SimpleType.” | Chỉ những kiểu Java được OpenType cho phép mới là open data hợp lệ. |
| “DynamicMBean luôn là Open MBean.” | \`DynamicMBean\` có thể công bố metadata/kiểu bất kỳ; Open MBean có yêu cầu về OpenType và OpenMBeanInfo. |
| “MXBean và Open MBean là cùng class.” | MXBean cung cấp mapping typed Java sang open data; Open MBean là mô hình metadata/open data có thể triển khai theo nhiều cách. |
| “JMX có sẵn pagination cho TabularData.” | API TabularData không tự cung cấp phân trang từ xa. |
| “Dữ liệu OpenType luôn được client hiểu đúng phiên bản.” | Client vẫn phải xử lý đổi tên, đổi kiểu và thay đổi schema. |

## 15. Bài tập thực hành

### Bài tập 1 — Một snapshot có schema

Tạo \`CompositeType\` tên \`ThreadPoolSnapshot\` với các field \`active: Integer\`, \`queued: Long\`, \`shutdown: Boolean\`. Khởi tạo \`CompositeDataSupport\` với giá trị phù hợp, sau đó đọc từng field. Thử truyền \`"10"\` cho \`queued\` và quan sát lỗi.

**Kết quả mong đợi:** hiểu việc schema khai báo \`SimpleType.LONG\` bắt buộc giá trị Java \`Long\` tương ứng, không phải một String số.

### Bài tập 2 — Bảng theo key

Tạo \`CompositeType\` \`WorkerRow\` gồm \`name: String\` và \`completed: Long\`; tạo \`TabularType\` dùng index \`name\`. Thêm hai worker, đọc qua \`get(new Object[] { "worker-1" })\`, sau đó thử thêm hàng có khóa trùng để quan sát quy tắc duy nhất.

**Kết quả mong đợi:** phân biệt index của bảng và thứ tự row, cũng như cách truy cập giá trị bằng khóa.

### Bài tập 3 — MBean thực tế

Chạy ví dụ \`OpenQueueMonitor\`, dùng \`ManagementFactory.getPlatformMBeanServer()\` và \`ObjectName\` để đăng ký. Đọc metadata của \`Snapshot\`, sau đó gọi \`reset\` và đọc lại.

**Kết quả mong đợi:** \`Snapshot.pending\` đổi từ 12 sang 0; JMX client không cần biết class \`QueueSnapshot\` giả định của nghiệp vụ.

### Bài tập 4 — Khả năng tương thích

Viết một client chỉ đọc \`pending\`. Mở rộng schema server bằng \`oldestAgeMs: Long\` và kiểm tra client có còn đọc được không. Sau đó đổi tên \`pending\` thành \`queued\` và quan sát sự khác biệt. Đề xuất cách version hóa schema phù hợp.

### Bài tập 5 — Spring adapter

Tạo một Spring service cung cấp snapshot queue, một JMX adapter chuyển snapshot sang \`CompositeData\`, và quản lý đăng ký adapter theo vòng đời Spring. Kiểm tra không đăng ký cùng \`ObjectName\` hai lần. Giải thích tại sao nên giữ logic nghiệp vụ ngoài adapter.

## 16. Câu hỏi ôn tập

**1. OpenType mô tả điều gì?** Mô tả kiểu dữ liệu chuẩn được phép trao đổi trong mô hình open data JMX.

**2. CompositeType khác CompositeData thế nào?** CompositeType là schema của bản ghi; CompositeData là một bản ghi cụ thể tuân theo schema đó.

**3. TabularType dùng indexNames để làm gì?** Định nghĩa những item của mỗi hàng dùng làm khóa nhận diện duy nhất trong TabularData.

**4. Vì sao open data giúp client từ xa?** Các kiểu và schema được biểu diễn bằng lớp JMX chuẩn, giảm phụ thuộc vào class nghiệp vụ riêng của server.

**5. ArrayType có luôn chấp nhận mảng primitive không?** Không. Cần khai báo kiểu array đúng quy tắc của \`ArrayType\`; \`Integer[]\` và \`int[]\` là hai dạng Java khác nhau.

**6. Tại sao không nên trả TabularData rất lớn?** Việc tạo, truyền và render toàn bộ bảng có thể tốn tài nguyên và không có cơ chế phân trang tự động.

**7. Có nên thay đổi kiểu \`pending\` từ LONG sang STRING mà giữ nguyên schema/version?** Không nên. Đây là thay đổi có thể phá client; cần hợp đồng tương thích hoặc version hóa rõ.

**8. MBeanServer giữ vai trò gì với Open MBean?** Nó là registry và điểm chuyển tiếp yêu cầu quản trị; Open MBean quyết định dữ liệu và metadata được công bố.

## 17. Tổng kết

**Open MBean** đưa cấu trúc quản trị về các kiểu dữ liệu có thể khám phá bằng JMX chuẩn. \`SimpleType\` diễn tả giá trị đơn; \`ArrayType\` mô tả mảng; \`CompositeType\` + \`CompositeData\` biểu diễn snapshot có các trường cố định; \`TabularType\` + \`TabularData\` biểu diễn tập hợp các hàng có khóa. \`OpenMBeanInfoSupport\` và những lớp metadata liên quan công bố schema của thuộc tính và operation.

Trong ứng dụng Spring Framework, có thể sử dụng exporter/MXBean khi phù hợp hoặc tạo adapter Open MBean rõ ràng cho dữ liệu quản trị phức tạp. Hãy bảo vệ thông tin, giữ schema ổn định, kiểm soát kích thước dữ liệu và gắn vòng đời đăng ký với vòng đời ứng dụng.

## Tài liệu tham khảo

- Java SE 21 — \`javax.management.openmbean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/package-summary.html
- Java SE 21 — \`CompositeData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — \`TabularData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Java SE 21 — \`OpenMBeanInfoSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/OpenMBeanInfoSupport.html
- Java SE 21 — \`javax.management.MXBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html