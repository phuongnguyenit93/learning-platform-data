# Ánh xạ kiểu Java sang Open Types trong MXBean (Java 17+, JMX)

## 1. Vấn đề mà MXBean giải quyết

Java có những kiểu dữ liệu tiện dụng như `List<String>`, `Map<String,Integer>`, `enum`, `record` và các JavaBean chứa thông tin quản trị. Tuy nhiên, một công cụ giám sát chung hoặc một client JMX khác tiến trình **không thể giả định có các class model riêng** của ứng dụng. MXBean cho phép interface Java biểu diễn dữ liệu theo kiểu tự nhiên, nhưng tự **ánh xạ chúng thành các Open Data types tiêu chuẩn** trước khi công bố qua JMX.

Bài **“Ánh xạ kiểu Java sang Open Types”**, thuộc chủ đề **MXBean**, giải thích cơ chế ánh xạ hiện hành của Java SE 26 và cách dùng an toàn. Sau bài học, bạn sẽ:
- Phân biệt Java type, `OpenType` (mô tả kiểu) và actual Open Data value.
- Hiểu bốn loại `SimpleType`, `ArrayType`, `CompositeType` và `TabularType`.
- Nắm mapping cho primitive/boxed, arrays, enum, collections, maps, records, JavaBeans, tham chiếu tới MXBean khác.
- Hiểu yêu cầu **reconstructible** khi một operation nhận tham số hoặc khi client dùng `JMX.newMXBeanProxy`.
- Biết cách đọc `MBeanInfo` descriptor `openType` và `originalType`.
- Thiết kế snapshot DTO, quản lý thay đổi schema, tránh các type không hỗ trợ.
- Biên dịch và chạy một bộ **63 kiểm thử Java 17+** với `MBeanServer` thật, không mở JMX remote listener.

**Chỉ sử dụng kiến thức hiện hành:** Java SE 26 vẫn định nghĩa MXBean trong module `java.management`. Record classes, `@javax.management.ConstructorParameters` và các quy tắc chuyển đổi dưới đây đều còn áp dụng. Chương trình ví dụ đã được kiểm thử thực tế trên OpenJDK 24 bằng `javac --release 17`, đạt **63/63 PASS**.

## 2. MXBean và Standard MBean không giống nhau ở đâu?

JMX dùng `MBeanServer` để đăng ký các đối tượng có thuộc tính (attributes) và thao tác quản trị (operations). Standard MBean có interface thường mang tên `SomethingMBean`. MXBean thường mang tên `SomethingMXBean` hoặc dùng annotation `@MXBean`.

Ví dụ:

```java
public interface InventoryMXBean {
    long getRequests();
    Snapshot getSnapshot();
    Map<String, Integer> getLimits();
}
```

Đây là **snippet**, các kiểu và imports phải được khai báo; `Snapshot` cần convertible. Khi registered như MXBean, interface có thể trả object business-friendly `Snapshot`; raw JMX client lại đọc một `CompositeData`, không nhất thiết phải biết class `Snapshot`.

| Nội dung | Standard MBean | MXBean |
| --- | --- | --- |
| Interface | `SomethingMBean` | `SomethingMXBean` hoặc `@MXBean` |
| Return/parameter types | Types trong interface Java, có thể application-specific | Types phải ánh xạ sang Open Types |
| Client tổng quát | Có thể cần class riêng của server | Dùng `CompositeData`/`TabularData` và scalar/arrays |
| Typed proxy | `JMX.newMBeanProxy` | `JMX.newMXBeanProxy` |
| Type metadata | `MBeanInfo` | `MBeanInfo` và descriptor `openType`/`originalType` |
| Mục tiêu | Management Java thuần | Management có wire/schema representation interoperable |

MXBean **không** tự đồng nghĩa với remote server, TLS hay authentication. Đây là một mô hình dữ liệu và MBean introspection.

## 3. Ba khái niệm: J, opentype(J), opendata(J)

Tài liệu MXBean chính thức mô tả mỗi Java type `J` thông qua:
1. `opentype(J)`: một đối tượng kế thừa `OpenType`, mô tả schema.
2. `opendata(J)`: Java class **thực sự được dùng** ở ranh giới Open Data.
3. Quy tắc đổi `J -> opendata(J)`.
4. Quy tắc đổi `opendata(J) -> J` nếu type **reconstructible**.

Ví dụ `List<String>`:

```text
Java method return: List<String>
          |
          v
OpenType: ArrayType(1, SimpleType.STRING)
          |
          v
Raw Open Data value: String[]
          |
          v
MBeanServer.getAttribute("Hosts"): String[]
          |
          v
JMX.newMXBeanProxy(...).getHosts(): List<String>
```

Không nhầm một `OpenType` descriptor với chính value. `SimpleType.STRING` **mô tả** cách biểu diễn chuỗi; value là `String`. `CompositeType` **mô tả** các item; value là `CompositeData`. `TabularType` **mô tả** bảng; value là `TabularData`.

### 3.1. Bốn loại OpenType hiện hành

| Lớp OpenType | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `SimpleType<T>` | Scalar hợp lệ | `SimpleType.INTEGER`, `SimpleType.STRING` |
| `ArrayType<T>` | Mảng một/nhiều chiều | `List<String>` → mảng String |
| `CompositeType` | Structure theo các item đặt tên | Record hoặc bean |
| `TabularType` | Table of CompositeData rows, có index | Map |

Raw data interface `CompositeData` và `TabularData` có thể được hiện thực bằng `CompositeDataSupport`/`TabularDataSupport`. Chương trình nên lập trình theo interfaces, không giả định một concrete class duy nhất.

### 3.2. Danh sách scalar không mở rộng tùy ý

`OpenType.ALLOWED_CLASSNAMES_LIST` bao gồm boxed primitives (`Boolean`, `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `Character`), `String`, `BigDecimal`, `BigInteger`, `Date`, `ObjectName`, `Void` và `CompositeData`/`TabularData` cho dữ liệu cấu trúc. Điều này **không** có nghĩa `CompositeData` là một `SimpleType`. Các giá trị composite và tabular có schema riêng.

`Serializable` không làm cho `Object` tùy ý trở thành Open Type. Việc một Java class có thể được serialize không bảo đảm MXBean có thể chuyển nó qua JMX raw interface.

## 4. Bảng mapping Java → OpenType → raw value

| Java type xuất hiện trên MXBean | OpenType | Runtime raw value |
| --- | --- | --- |
| `boolean` | `SimpleType.BOOLEAN` | `Boolean` |
| `byte`, `short`, `int`, `long` | `SimpleType.BYTE/SHORT/INTEGER/LONG` | Boxed type |
| `float`, `double`, `char` | `SimpleType.FLOAT/DOUBLE/CHARACTER` | Boxed type |
| `Integer`, `Long`, `String` | `SimpleType` tương ứng | Cùng class |
| `BigDecimal`, `BigInteger` | `SimpleType.BIGDECIMAL/BIGINTEGER` | Cùng class |
| `java.util.Date` | `SimpleType.DATE` | Date |
| `ObjectName` | `SimpleType.OBJECTNAME` | ObjectName |
| `int[]` | `ArrayType.getPrimitiveArrayType(int[].class)` | `int[]` |
| `int[][]` | ArrayType nhiều chiều | `int[][]` |
| `String[]` | ArrayType 1D của SimpleType.STRING | String[] |
| `List<String>` | Giống String[] | String[] |
| `Set<Integer>` | Giống Integer[] | Integer[] |
| `SortedSet<String>` | Giống String[] (có điều kiện) | String[] |
| `enum Mode` | `SimpleType.STRING` | String chứa tên enum |
| `Map<String,Integer>` | `TabularType` | `TabularData` |
| `SortedMap<String,String>` | TabularType (có điều kiện) | TabularData |
| `record Snapshot(...)` | CompositeType khi components convertible | CompositeData |
| JavaBean có getters convertible | CompositeType | CompositeData |
| `List<Snapshot>` | ArrayType của CompositeType | CompositeData[] |
| `Map<String,Snapshot>` | TabularType có value CompositeType | TabularData |
| Một interface `ChildMXBean` | SimpleType.OBJECTNAME | ObjectName |

`void` của operation return thuộc trường hợp riêng `SimpleType.VOID` trong descriptor; không dùng `void` làm attribute data. Null có thể map giữa reference types/Open Data types nhưng primitive Java không thể nhận null.

### 4.1. Primitive/boxed và mảng primitive

`long getRequests()` có raw value `Long`. Nhưng `int[] getCounters()` có raw value **`int[]`**, không phải `Integer[]`. Với `int[][]`, runtime vẫn là mảng 2 chiều tương ứng. ArrayType có cấu trúc dành riêng cho primitive arrays; đừng suy toàn bộ mảng phải box từng phần tử.

```java
int[] counters = {3, 5};
int[][] matrix = {{1, 2}, {3, 4}};
```

Nếu expose các biến trên qua MXBean, raw `MBeanServer.getAttribute` sẽ trả mảng primitive tương ứng. Fixture kiểm tra cả hai.

### 4.2. Enum thành String

```java
enum Mode { READY, BUSY }
```

Trên một MXBean có `Mode getMode()` hoặc `void setMode(Mode)`:
- Raw getter trả `"READY"`/`"BUSY"` dưới dạng `String`.
- Raw setter `MBeanServer.setAttribute(... new Attribute("Mode", "BUSY"))` truyền một string.
- Typed `JMX.newMXBeanProxy` dựng enum constant khi trả về.
- Với operation `Mode echoMode(Mode)`, raw invoke dùng string parameter type/signature.

Không đổi tùy tiện tên enum values của một schema quản trị đã được tích hợp: client model cũ có thể không dựng được hằng enum lạ.

### 4.3. List, Set, SortedSet → ArrayType

`List<E>`, `Set<E>`, `SortedSet<E>` được map như `E[]` nếu `E` convertible.

```java
List<String> hosts = List.of("node-a", "node-b");
Set<Integer> ports = Set.of(8080, 9090);
SortedSet<String> regions =
        new TreeSet<>(Set.of("apac", "eu"));
```

Raw values:
- Hosts là `String[]`.
- Ports là `Integer[]`.
- Regions là `String[]`.

Typed inverse:
- List → `ArrayList`.
- Set → `HashSet`.
- SortedSet → `TreeSet`.

**Thứ tự Set không phải contract.** Trong tests, so các phần tử của Set như một tập, không đối chiếu theo vị trí của mảng. `SortedSet<E>` chỉ convertible nếu element type implements `Comparable`. Conversion từ một SortedSet có `comparator()!=null` có thể ném `IllegalArgumentException`, kể cả comparator đã dùng để sắp xếp hoàn toàn hợp lệ trong Java.

### 4.4. Map, SortedMap → TabularData

Với `Map<K,V>`, framework tạo `TabularType` mà mỗi row `CompositeData` có **hai item `key` và `value`**, index key là item `key`.

```java
Map<String, Integer> limits =
        Map.of("read", 10, "write", 20);
```

Dữ liệu raw là một bảng có hai rows. Truy xuất:

```java
TabularData table = (TabularData)
        mbeanServer.getAttribute(objectName, "Limits");
CompositeData row = table.get(new Object[]{"read"});
int readLimit = (Integer) row.get("value");
```

Đây là **snippet** cần biến mbeanServer/objectName đã khởi tạo. Với `Map<String,Snapshot>`, row `value` lại là `CompositeData`. Với `SortedMap`, key type phải implements Comparable và runtime map dùng comparator khác null có thể khiến conversion lỗi.

Proxy có thể dựng Map thành `HashMap` và SortedMap thành `TreeMap`. Đừng mong Open Data tự bảo toàn insertion order của một concrete Map implementation. Tránh map keys mutable, null hoặc không có ánh xạ được xác định.

## 5. Record và JavaBean → CompositeType

### 5.1. Record — cấu trúc immutable rất phù hợp

```java
public record Snapshot(
        long requests,
        String state,
        List<String> zones) {}
```

Record chuyển được sang `CompositeType` nếu **mọi component** convertible. Raw `CompositeData` có keys:
- `requests`: `Long`.
- `state`: `String`.
- `zones`: `String[]`.

Typed proxy dùng **canonical constructor** dựng lại record, không cần `@ConstructorParameters`. Record không có component nào là **không convertible** theo JDK 26 spec. List<Snapshot> raw là `CompositeData[]`; Map<String,Snapshot> raw là TabularData có nested CompositeData.

### 5.2. JavaBean getters quyết định items

```java
public final class Sample {
    private final int count;
    private final String comment;

    public int getCount() { return count; }
    public String getComment() { return comment; }
}
```

Đây chỉ là **snippet về getters** (không biên dịch một mình vì chưa gán final fields). Mapped CompositeData dùng item `count` và `comment`. Quy tắc JavaBean lowercases chữ đầu item:
- Getter `getCount()` trong object → item `count`.
- Getter `getName()` trong object → item `name`.
- Getter `isReady()` trong object → item `ready`.

**Khác với MXBean attribute naming:** Trên chính interface MXBean, `getRequests()` tạo attribute `Requests` (R hoa), trong record/bean CompositeData nó là `requests` (r thường). `Object.getClass()` được bỏ qua khi phân tích getter. Nếu hai getters tạo trùng item name hoặc một getter có type không convertible, class có thể không được map.

### 5.3. CompositeDataView

Nếu custom type implements `javax.management.openmbean.CompositeDataView`, JMX có thể gọi `toCompositeData(CompositeType)` để chuyển đổi thay cho việc tự gọi từng getter; đây là advanced customization. Dù tự tạo CompositeData, nó vẫn phải tuân schema CompositeType và requirements của ứng dụng. Không dùng hook này để đưa secrets/objects không được phép qua Open Data boundary.

## 6. Reconstructible — mapping ngược mới quyết định proxy

**Convertible** nghĩa Java type có thể chuyển thành Open Data. **Reconstructible** nghĩa Open Data có thể quay trở lại Java type ban đầu.

Mọi parameter của MXBean method phải reconstructible, bởi server nhận raw values và cần truyền Java arguments cho implementation. Trong `JMX.newMXBeanProxy`, kiểu return value phải reconstructible thì typed client mới có thể dựng Java object.

Javadoc Java SE 26 quy định các cơ chế tái dựng theo thứ tự ưu tiên:

1. `public static T from(CompositeData cd)` trong type T.
2. Với `record`, canonical constructor nếu components hiện diện.
3. Public constructor annotated `@javax.management.ConstructorParameters` hoặc `@java.beans.ConstructorProperties`, với names/types khớp getters.
4. Public no-arg constructor và setters tương ứng **mọi getter**.
5. Interface chỉ có getters, được dựng thành proxy backing CompositeData.
6. Nếu không có cách nào phù hợp → không reconstructible.

Nếu một item con không reconstructible, DTO chứa nó cũng không reconstructible theo chiều ngược. Không ép kiểu `(MyBean) compositeData`: raw `CompositeData` không phải object MyBean.

### 6.1. Static factory from(CompositeData)

```java
public final class LegacySample {
    private final int count;
    private final String comment;

    private LegacySample(int count, String comment) {
        this.count = count;
        this.comment = comment;
    }
    public int getCount() { return count; }
    public String getComment() { return comment; }

    public static LegacySample from(CompositeData data) {
        return new LegacySample(
                (Integer) data.get("count"),
                (String) data.get("comment"));
    }
}
```

Đây là **snippet đầy đủ của class** nếu có import CompositeData. Raw JMX vẫn trả CompositeData. Typed proxy gọi static from để dựng immutable `LegacySample`. Nếu raw data không hợp lệ, application có thể throw exception có ngữ nghĩa thay vì âm thầm bỏ qua invariants.

### 6.2. ConstructorParameters không phụ thuộc java.desktop

```java
public final class ConstructedValue {
    private final int code;
    private final String label;

    @javax.management.ConstructorParameters({"code", "label"})
    public ConstructedValue(int code, String label) {
        this.code = code;
        this.label = label;
    }

    public int getCode() { return code; }
    public String getLabel() { return label; }
}
```

`@javax.management.ConstructorParameters` hiện hành thuộc module `java.management`. `@java.beans.ConstructorProperties` cũng được đặc tả hỗ trợ nhưng nằm ở module `java.desktop`. Trong runtime `jlink` không bao gồm `java.desktop`, nên đối với Java code quản trị hiện đại dùng `javax.management.ConstructorParameters` có ưu thế rõ ràng.

Javadoc nói nếu một constructor có cả hai annotations, `javax.management.ConstructorParameters` được ưu tiên. Constructor annotated phải có tên tham số tương ứng chính xác với getters/types; không thể dùng tên trường khác tùy ý.

### 6.3. Mutable bean và getter-only interface

No-arg public constructor kèm setters là cách reconstruct hợp lệ nhưng thường kém phù hợp cho immutable management snapshots. Một interface chỉ có getters cũng có thể được dựng thành proxy dựa trên `CompositeDataInvocationHandler`. Nên chọn cấu trúc ít mutable nhất mà ứng dụng có thể dùng để tránh data race và invariant mismatch.

## 7. Tham chiếu một MXBean khác không serialize object

Một MXBean interface có thể tham chiếu interface MXBean khác:

```java
public interface ChildMXBean {
    String getId();
}

public interface InventoryMXBean {
    ChildMXBean getChild();
}
```

Raw `InventoryMXBean.Child` trả **`ObjectName`**, OpenType `SimpleType.OBJECTNAME`. Vì framework cần name để định vị child, **cả parent và child phải được đăng ký trong cùng MBeanServer**. Typed proxy cho parent có thể dựng một proxy ChildMXBean để tiếp tục gọi `getId()`.

Với object chưa đăng ký, mapping reference không thể đảm bảo ObjectName có nghĩa. Đừng register cùng MXBean object dưới nhiều ObjectNames trong cùng MBeanServer: Java SE 26 spec nêu đó là ambiguity đối với references.

## 8. Metadata: descriptor openType và originalType

`MBeanServer.getMBeanInfo(name)` trả `MBeanInfo`. Đối với MXBean, `MBeanInfo` **không phải lúc nào cũng là `OpenMBeanInfo`** vì yêu cầu tương thích.

Mỗi `MBeanAttributeInfo`, `MBeanParameterInfo` và `MBeanOperationInfo` có descriptor fields:
- `JMX.OPEN_TYPE_FIELD` (`"openType"`) → `OpenType<?>` thực tế.
- `JMX.ORIGINAL_TYPE_FIELD` (`"originalType"`) → string biểu diễn Java type gốc.

Đặc biệt, `getRequests()` trả primitive `long`:
- `MBeanAttributeInfo.getType()` có thể là chuỗi `"long"`.
- Descriptor `openType` là `SimpleType.LONG`.
- Giá trị raw là boxed `Long`.

`MBeanInfo` descriptor có field `mxbean` với giá trị **chuỗi `"true"`**, không phải Boolean.TRUE. Đây là chi tiết đã được xác minh trong fixture.

```java
MBeanInfo info = mbs.getMBeanInfo(objectName);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    Object schema = attr.getDescriptor()
            .getFieldValue(JMX.OPEN_TYPE_FIELD);
    Object javaType = attr.getDescriptor()
            .getFieldValue(JMX.ORIGINAL_TYPE_FIELD);
    System.out.println(attr.getName()
            + " : " + javaType + " -> " + schema);
}
```

Snippet này cần `mbs`/`objectName` đã khởi tạo. Trong chương trình thật, schema introspection rất hữu ích cho generic monitoring tools, nhưng đừng in raw giá trị nhạy cảm của mọi attributes.

## 9. Tạo một MXBean thật và kiểm tra 63 trường hợp

Bộ `MXBeanOpenTypesDemo.java` là một chương trình **Java 17+ độc lập** dùng JDK tiêu chuẩn, không cần library ngoài.

Nó:
- Tạo `MBeanServerFactory.newMBeanServer("example")` trong JVM, không mở cổng JMX remote.
- Register `InventoryMXBean` và `ChildMXBean` dưới ObjectNames.
- Publish scalar, BigDecimal, Date, ObjectName, enum, primitive arrays, collections, maps, records, JavaBeans.
- Dùng `MBeanServer.getAttribute` để kiểm tra **raw Open Data values** và `getMBeanInfo` descriptors.
- Dùng `JMX.newMXBeanProxy` để kiểm tra chuyển ngược từ Open Data sang Java types.
- Thử `MBeanServer.invoke` với operation integer và enum.
- Thử raw/typed setter `Mode` hai chiều.
- Xác nhận `BadMXBean` có return `Object` bị từ chối bởi `NotCompliantMBeanException`.
- Unregister hai objects trong `finally`, không để thay đổi global platform MBeanServer.

**QA:** 63 assertions được chạy thành công trên OpenJDK 24 với compiler `javac --release 17`; không có networking, RMI, credential hay data của hệ thống cần thu thập.

### 9.1. File chạy hoàn chỉnh — `MXBeanOpenTypesDemo.java`

Lưu toàn bộ source sau vào file có đúng tên:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import javax.management.Attribute;
import javax.management.JMX;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotCompliantMBeanException;
import javax.management.ObjectName;
import javax.management.openmbean.ArrayType;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;
import javax.management.openmbean.TabularData;
import javax.management.openmbean.TabularType;

public final class MXBeanOpenTypesDemo {
    private static int passed;

    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    public enum Mode { READY, BUSY }

    public record Snapshot(long requests, String state, List<String> zones) {}

    public static final class LegacySample {
        private final int count;
        private final String comment;

        private LegacySample(int count, String comment) {
            this.count = count;
            this.comment = comment;
        }

        public int getCount() { return count; }
        public String getComment() { return comment; }

        public static LegacySample from(CompositeData data) {
            return new LegacySample(
                    (Integer) data.get("count"),
                    (String) data.get("comment"));
        }
    }

    public static final class ConstructedValue {
        private final int code;
        private final String label;

        @javax.management.ConstructorParameters({"code", "label"})
        public ConstructedValue(int code, String label) {
            this.code = code;
            this.label = label;
        }

        public int getCode() { return code; }
        public String getLabel() { return label; }
    }

    public interface ChildMXBean {
        String getId();
    }

    public static final class Child implements ChildMXBean {
        @Override public String getId() { return "child-1"; }
    }

    public interface InventoryMXBean {
        String getName();
        long getRequests();
        boolean isHealthy();
        BigDecimal getThreshold();
        Date getUpdatedAt();
        ObjectName getDependencyName();
        Mode getMode();
        int[] getCounters();
        int[][] getMatrix();
        List<String> getHosts();
        Set<Integer> getPorts();
        SortedSet<String> getRegions();
        Map<String, Integer> getLimits();
        SortedMap<String, String> getAliases();
        Snapshot getSnapshot();
        List<Snapshot> getSnapshots();
        Map<String, Snapshot> getSnapshotIndex();
        LegacySample getLegacySample();
        ConstructedValue getConstructedValue();
        ChildMXBean getChild();
        int add(int left, int right);
        Mode echoMode(Mode mode);
        void setMode(Mode mode);
    }

    public static final class Inventory implements InventoryMXBean {
        private final Child child;
        private final ObjectName dependencyName;
        private Mode mode = Mode.READY;

        Inventory(Child child, ObjectName dependencyName) {
            this.child = child;
            this.dependencyName = dependencyName;
        }

        @Override public String getName() { return "inventory"; }
        @Override public long getRequests() { return 42; }
        @Override public boolean isHealthy() { return true; }
        @Override public BigDecimal getThreshold() {
            return new BigDecimal("12.50");
        }
        @Override public Date getUpdatedAt() { return new Date(0); }
        @Override public ObjectName getDependencyName() {
            return dependencyName;
        }
        @Override public Mode getMode() { return mode; }
        @Override public void setMode(Mode mode) { this.mode = mode; }
        @Override public int[] getCounters() { return new int[]{3, 5}; }
        @Override public int[][] getMatrix() {
            return new int[][]{{1, 2}, {3, 4}};
        }
        @Override public List<String> getHosts() {
            return List.of("node-a", "node-b");
        }
        @Override public Set<Integer> getPorts() {
            return Set.of(8080, 9090);
        }
        @Override public SortedSet<String> getRegions() {
            return new TreeSet<>(Set.of("apac", "eu"));
        }
        @Override public Map<String, Integer> getLimits() {
            return Map.of("read", 10, "write", 20);
        }
        @Override public SortedMap<String, String> getAliases() {
            SortedMap<String, String> result = new TreeMap<>();
            result.put("a", "alpha");
            result.put("b", "beta");
            return result;
        }
        @Override public Snapshot getSnapshot() {
            return new Snapshot(42, "ready", List.of("apac", "eu"));
        }
        @Override public List<Snapshot> getSnapshots() {
            return List.of(new Snapshot(1, "ready", List.of("apac")),
                    new Snapshot(2, "busy", List.of("eu")));
        }
        @Override public Map<String, Snapshot> getSnapshotIndex() {
            return Map.of("main", getSnapshot());
        }
        @Override public LegacySample getLegacySample() {
            return new LegacySample(7, "compat");
        }
        @Override public ConstructedValue getConstructedValue() {
            return new ConstructedValue(9, "annotation");
        }
        @Override public ChildMXBean getChild() {
            return child;
        }
        @Override public int add(int left, int right) {
            return left + right;
        }
        @Override public Mode echoMode(Mode mode) { return mode; }
    }

    public interface BadMXBean {
        Object getArbitrary();
    }

    public static final class Bad implements BadMXBean {
        @Override public Object getArbitrary() { return new Object(); }
    }

    static MBeanAttributeInfo attribute(MBeanInfo info, String name) {
        for (MBeanAttributeInfo a : info.getAttributes()) {
            if (name.equals(a.getName())) return a;
        }
        throw new AssertionError("Missing JMX attribute " + name);
    }

    static OpenType<?> openType(MBeanInfo info, String attr) {
        Object value = attribute(info, attr).getDescriptor()
                .getFieldValue(JMX.OPEN_TYPE_FIELD);
        if (!(value instanceof OpenType<?> openType)) {
            throw new AssertionError("No OpenType for " + attr);
        }
        return openType;
    }

    public static void main(String[] args) throws Exception {
        MBeanServer mbs = MBeanServerFactory.newMBeanServer("example");
        ObjectName inventoryName = new ObjectName("example:type=Inventory");
        ObjectName childName = new ObjectName("example:type=Child");
        Child child = new Child();
        Inventory inventory = new Inventory(child, childName);
        try {
            mbs.registerMBean(child, childName);
            mbs.registerMBean(inventory, inventoryName);

            check("mxbean-interface-recognized",
                    JMX.isMXBeanInterface(InventoryMXBean.class));
            check("child-mxbean-interface-recognized",
                    JMX.isMXBeanInterface(ChildMXBean.class));
            check("local-mbean-registered",
                    mbs.isRegistered(inventoryName));
            MBeanInfo info = mbs.getMBeanInfo(inventoryName);
            check("mxbean-descriptor-flag",
                    "true".equals(String.valueOf(
                            info.getDescriptor().getFieldValue(
                                    JMX.MXBEAN_FIELD))));

            check("string-simple-open-type",
                    openType(info, "Name").equals(SimpleType.STRING));
            check("long-simple-open-type",
                    openType(info, "Requests").equals(SimpleType.LONG));
            check("boolean-simple-open-type",
                    openType(info, "Healthy").equals(SimpleType.BOOLEAN));
            check("bigdecimal-simple-open-type",
                    openType(info, "Threshold").equals(
                            SimpleType.BIGDECIMAL));
            check("date-simple-open-type",
                    openType(info, "UpdatedAt").equals(SimpleType.DATE));
            check("objectname-simple-open-type",
                    openType(info, "DependencyName").equals(
                            SimpleType.OBJECTNAME));
            check("enum-maps-to-simple-string",
                    openType(info, "Mode").equals(SimpleType.STRING));
            check("primitive-int-array-open-type",
                    openType(info, "Counters").equals(
                            ArrayType.getPrimitiveArrayType(int[].class)));
            check("multidimensional-primitive-array-open-type",
                    openType(info, "Matrix") instanceof ArrayType<?>
                    && ((ArrayType<?>) openType(info, "Matrix"))
                            .getDimension() == 2);
            check("list-maps-to-array-open-type",
                    openType(info, "Hosts").equals(
                            new ArrayType<>(1, SimpleType.STRING)));
            check("set-maps-to-array-open-type",
                    openType(info, "Ports").equals(
                            new ArrayType<>(1, SimpleType.INTEGER)));
            check("sortedset-maps-to-array-open-type",
                    openType(info, "Regions").equals(
                            new ArrayType<>(1, SimpleType.STRING)));
            check("map-maps-to-tabular-type",
                    openType(info, "Limits") instanceof TabularType);
            check("sortedmap-maps-to-tabular-type",
                    openType(info, "Aliases") instanceof TabularType);
            check("record-maps-to-composite-type",
                    openType(info, "Snapshot") instanceof CompositeType);
            check("list-of-records-maps-to-array",
                    openType(info, "Snapshots") instanceof ArrayType<?>);
            check("map-of-records-maps-to-tabular",
                    openType(info, "SnapshotIndex")
                            instanceof TabularType);
            check("constructor-annotated-bean-maps-to-composite",
                    openType(info, "ConstructedValue")
                            instanceof CompositeType);
            check("primitive-attribute-metadata-original-type",
                    attribute(info, "Requests").getType().equals("long"));
            check("bean-maps-to-composite-type",
                    openType(info, "LegacySample")
                            instanceof CompositeType);
            check("mxbean-reference-maps-to-objectname",
                    openType(info, "Child").equals(
                            SimpleType.OBJECTNAME));
            check("original-java-type-retained-in-descriptor",
                    String.valueOf(attribute(info, "Hosts")
                            .getDescriptor().getFieldValue(
                                    JMX.ORIGINAL_TYPE_FIELD))
                            .contains("java.util.List"));

            check("raw-long-is-boxed",
                    mbs.getAttribute(inventoryName, "Requests")
                            instanceof Long);
            check("raw-boolean-is-boxed",
                    mbs.getAttribute(inventoryName, "Healthy")
                            instanceof Boolean);
            check("raw-enum-is-string",
                    "READY".equals(
                            mbs.getAttribute(inventoryName, "Mode")));
            check("raw-list-is-string-array",
                    Arrays.equals((String[]) mbs.getAttribute(
                            inventoryName, "Hosts"),
                            new String[] {"node-a", "node-b"}));
            Object[] ports = (Object[]) mbs.getAttribute(
                    inventoryName, "Ports");
            check("raw-set-is-integer-array",
                    ports.length == 2
                            && Arrays.asList(ports)
                            .containsAll(List.of(8080, 9090)));
            check("raw-primitive-array-is-primitive-array",
                    Arrays.equals((int[]) mbs.getAttribute(
                            inventoryName, "Counters"),
                            new int[] {3, 5}));
            check("raw-nested-primitive-array",
                    Arrays.deepEquals((int[][]) mbs.getAttribute(
                            inventoryName, "Matrix"),
                            new int[][] {{1, 2}, {3, 4}}));
            TabularData rawMap = (TabularData) mbs.getAttribute(
                    inventoryName, "Limits");
            check("raw-map-is-tabular-data",
                    rawMap.size() == 2
                    && rawMap.getTabularType().getIndexNames()
                            .equals(List.of("key")));
            check("tabular-row-has-key-value",
                    ((Integer)((CompositeData) rawMap.get(
                            new Object[] {"read"})).get("value")) == 10);
            check("raw-sorted-map-is-tabular-data",
                    mbs.getAttribute(inventoryName, "Aliases")
                            instanceof TabularData);
            CompositeData rawRecord = (CompositeData)
                    mbs.getAttribute(inventoryName, "Snapshot");
            check("raw-record-is-compositedata",
                    rawRecord.get("requests").equals(42L)
                    && rawRecord.get("state").equals("ready"));
            check("record-list-field-maps-to-string-array",
                    Arrays.equals(
                            (String[]) rawRecord.get("zones"),
                            new String[] {"apac", "eu"}));
            check("raw-list-of-records-compositedata-array",
                    mbs.getAttribute(inventoryName, "Snapshots")
                            instanceof CompositeData[]);
            TabularData rawIndex = (TabularData) mbs.getAttribute(
                    inventoryName, "SnapshotIndex");
            check("raw-tabular-map-nested-composite",
                    ((CompositeData)((CompositeData) rawIndex.get(
                            new Object[] {"main"})).get("value"))
                            .get("state").equals("ready"));
            CompositeData rawBean = (CompositeData)
                    mbs.getAttribute(inventoryName, "LegacySample");
            check("raw-bean-compositedata-getters",
                    rawBean.get("count").equals(7)
                    && rawBean.get("comment").equals("compat"));
            CompositeData rawConstructed = (CompositeData)
                    mbs.getAttribute(inventoryName, "ConstructedValue");
            check("raw-constructor-annotated-bean-composite",
                    rawConstructed.get("code").equals(9)
                    && rawConstructed.get("label").equals("annotation"));
            check("raw-mxbean-reference-is-objectname",
                    childName.equals(mbs.getAttribute(
                            inventoryName, "Child")));

            InventoryMXBean proxy = JMX.newMXBeanProxy(
                    mbs, inventoryName, InventoryMXBean.class);
            check("proxy-long-return",
                    proxy.getRequests() == 42);
            check("proxy-enum-reconstructed",
                    proxy.getMode() == Mode.READY);
            check("proxy-list-reconstructed",
                    proxy.getHosts().equals(
                            List.of("node-a", "node-b")));
            check("proxy-set-reconstructed",
                    proxy.getPorts().equals(
                            Set.of(8080, 9090)));
            check("proxy-sortedset-reconstructed",
                    proxy.getRegions().equals(
                            new TreeSet<>(Set.of("apac", "eu"))));
            check("proxy-map-reconstructed",
                    proxy.getLimits().equals(
                            Map.of("read", 10, "write", 20)));
            check("proxy-sortedmap-reconstructed",
                    proxy.getAliases().firstKey().equals("a"));
            check("proxy-record-reconstructed",
                    proxy.getSnapshot().equals(
                            new Snapshot(42, "ready",
                                    List.of("apac", "eu"))));
            check("proxy-list-record-reconstructed",
                    proxy.getSnapshots().size() == 2
                    && proxy.getSnapshots().get(1).state().equals("busy"));
            check("proxy-map-record-reconstructed",
                    proxy.getSnapshotIndex().get("main")
                            .requests() == 42);
            check("proxy-bean-static-from",
                    proxy.getLegacySample().getCount() == 7);
            check("proxy-constructor-annotated-bean-reconstructed",
                    proxy.getConstructedValue().getCode() == 9
                    && proxy.getConstructedValue().getLabel()
                            .equals("annotation"));
            check("proxy-mxbean-reference",
                    proxy.getChild().getId().equals("child-1"));

            check("raw-add-operation",
                    mbs.invoke(inventoryName, "add",
                            new Object[]{2, 3},
                            new String[]{"int", "int"})
                            .equals(5));
            check("raw-enum-param-string",
                    mbs.invoke(inventoryName, "echoMode",
                            new Object[]{"BUSY"},
                            new String[]{"java.lang.String"})
                            .equals("BUSY"));
            check("proxy-enum-parameter",
                    proxy.echoMode(Mode.BUSY) == Mode.BUSY);
            proxy.setMode(Mode.BUSY);
            check("proxy-setter-enum",
                    proxy.getMode() == Mode.BUSY);
            mbs.setAttribute(inventoryName,
                    new Attribute("Mode", "READY"));
            check("raw-setter-enum-string",
                    proxy.getMode() == Mode.READY);

            boolean invalidRejected = false;
            try {
                mbs.registerMBean(new Bad(),
                        new ObjectName("example:type=Bad"));
            } catch (NotCompliantMBeanException expected) {
                invalidRejected = true;
            }
            check("unmapped-object-type-rejected",
                    invalidRejected);

            // Every check uses local MBeanServer only; no JMX remote listener.
            check("jmx-open-type-class-hierarchy",
                    OpenType.class.isAssignableFrom(
                            SimpleType.class)
                    && OpenType.class.isAssignableFrom(
                            CompositeType.class)
                    && OpenType.class.isAssignableFrom(
                            TabularType.class)
                    && OpenType.class.isAssignableFrom(
                            ArrayType.class));
            System.out.println("passed=" + passed);
        } finally {
            if (mbs.isRegistered(inventoryName))
                mbs.unregisterMBean(inventoryName);
            if (mbs.isRegistered(childName))
                mbs.unregisterMBean(childName);
        }
    }
}
```

### 9.2. Biên dịch và chạy

Trong thư mục chứa `MXBeanOpenTypesDemo.java`:

```bash
javac --release 17 -encoding UTF-8 MXBeanOpenTypesDemo.java
java MXBeanOpenTypesDemo
```

Các class JMX nằm trong module `java.management`. Nếu tạo **named module** riêng, thêm:

```java
module example.management {
    requires java.management;
}
```

Snippet `module-info.java` này chỉ dành cho project JPMS có package và source layout hợp lệ; fixture mặc định chạy classpath nên không phải thêm module-info vào cạnh source hiện tại.

### 9.3. Stdout đã kiểm chứng trên OpenJDK 24

```text
PASS mxbean-interface-recognized
PASS child-mxbean-interface-recognized
PASS local-mbean-registered
PASS mxbean-descriptor-flag
PASS string-simple-open-type
PASS long-simple-open-type
PASS boolean-simple-open-type
PASS bigdecimal-simple-open-type
PASS date-simple-open-type
PASS objectname-simple-open-type
PASS enum-maps-to-simple-string
PASS primitive-int-array-open-type
PASS multidimensional-primitive-array-open-type
PASS list-maps-to-array-open-type
PASS set-maps-to-array-open-type
PASS sortedset-maps-to-array-open-type
PASS map-maps-to-tabular-type
PASS sortedmap-maps-to-tabular-type
PASS record-maps-to-composite-type
PASS list-of-records-maps-to-array
PASS map-of-records-maps-to-tabular
PASS constructor-annotated-bean-maps-to-composite
PASS primitive-attribute-metadata-original-type
PASS bean-maps-to-composite-type
PASS mxbean-reference-maps-to-objectname
PASS original-java-type-retained-in-descriptor
PASS raw-long-is-boxed
PASS raw-boolean-is-boxed
PASS raw-enum-is-string
PASS raw-list-is-string-array
PASS raw-set-is-integer-array
PASS raw-primitive-array-is-primitive-array
PASS raw-nested-primitive-array
PASS raw-map-is-tabular-data
PASS tabular-row-has-key-value
PASS raw-sorted-map-is-tabular-data
PASS raw-record-is-compositedata
PASS record-list-field-maps-to-string-array
PASS raw-list-of-records-compositedata-array
PASS raw-tabular-map-nested-composite
PASS raw-bean-compositedata-getters
PASS raw-constructor-annotated-bean-composite
PASS raw-mxbean-reference-is-objectname
PASS proxy-long-return
PASS proxy-enum-reconstructed
PASS proxy-list-reconstructed
PASS proxy-set-reconstructed
PASS proxy-sortedset-reconstructed
PASS proxy-map-reconstructed
PASS proxy-sortedmap-reconstructed
PASS proxy-record-reconstructed
PASS proxy-list-record-reconstructed
PASS proxy-map-record-reconstructed
PASS proxy-bean-static-from
PASS proxy-constructor-annotated-bean-reconstructed
PASS proxy-mxbean-reference
PASS raw-add-operation
PASS raw-enum-param-string
PASS proxy-enum-parameter
PASS proxy-setter-enum
PASS raw-setter-enum-string
PASS unmapped-object-type-rejected
PASS jmx-open-type-class-hierarchy
passed=63
```

**Kết quả:** `javac --release 17` PASS, `java MXBeanOpenTypesDemo` PASS với **63/63 assertions**. Một local MBeanServer được tạo và dọn sạch. Các rows của Map/Set không dựa vào thứ tự iteration ngẫu nhiên.

### 9.4. Nhóm assertions quan trọng

| Nhóm | Assertions tiêu biểu | Điều được chứng minh |
| --- | --- | --- |
| MXBean identification | `mxbean-interface-recognized` | Interface hậu tố MXBean được công nhận |
| Metadata | `mxbean-descriptor-flag`, `original-java-type-retained-in-descriptor` | Descriptor phân biệt schema/gốc |
| Scalar | `long/boolean/bigdecimal-simple-open-type` | SimpleType đúng |
| Arrays | `primitive-int-array-open-type`, `multidimensional-primitive-array-open-type` | Mảng primitive giữ type |
| Collections | `list/set/sortedset-maps-to-array-open-type` | List/Set → arrays |
| Maps | `map-maps-to-tabular-type`, `tabular-row-has-key-value` | Map → TabularData |
| Record | `raw-record-is-compositedata` | Record → CompositeData |
| Nested data | `raw-tabular-map-nested-composite` | Map<String,Snapshot> → TabularData chứa CompositeData |
| Inverse record | `proxy-record-reconstructed` | Canonical constructor |
| Inverse bean | `proxy-bean-static-from` | Static from(CompositeData) |
| Annotated constructor | `proxy-constructor-annotated-bean-reconstructed` | ConstructorParameters |
| Enum | `raw-enum-is-string`, `proxy-enum-parameter` | String ↔ enum |
| MXBean reference | `raw-mxbean-reference-is-objectname`, `proxy-mxbean-reference` | ObjectName ↔ child proxy |
| Unsupported | `unmapped-object-type-rejected` | Return Object không convertible |

Không hiểu “63/63” là chứng minh tất cả Java classes sẽ convert được; tests chỉ bao phủ types đã nêu. Tài liệu Java SE 26 cung cấp các ràng buộc cho những kiểu còn lại.

## 10. Lỗi phổ biến trong MXBean mapping

**1. Nghĩ generic raw JMX sẽ trả Java List/Map/Record.**  
Không: List → array, Map → TabularData, record → CompositeData.

**2. Lẫn schema với value.**  
`CompositeType`/`TabularType` là schema, `CompositeData`/`TabularData` mới là value.

**3. Box mọi primitive arrays.**  
`int[]` raw không biến thành `Integer[]`.

**4. Coi enum được truyền như enum Java.**  
Raw value là tên constant dạng `String`; proxy mới dựng lại enum.

**5. Dựa vào thứ tự của Set.**  
`Set` không bảo đảm iteration order, không nên kiểm tra arrays theo vị trí.

**6. Dùng SortedSet/SortedMap có custom Comparator.**  
MXBean mapping yêu cầu natural Comparable và có thể fail nếu comparator khác null.

**7. Đưa `Object`, `Stream<T>` hoặc raw generic collection vào interface mà không kiểm tra mapping.**  
Chỉ dùng types được spec hỗ trợ hoặc DTO có getter/record components convertible.

**8. Nghĩ Serializable giải quyết mọi lỗi.**  
MXBean không dùng Java serialization như một cơ chế thay thế tự động cho Open Types.

**9. Dùng recursive object graph trong CompositeType.**  
Một type như `Node getNext()` tự tham chiếu không convertible; cần flatten thành IDs hoặc danh sách không đệ quy.

**10. Getter name trùng ở JavaBean.**  
`getOwner()` và `isOwner()` cùng map sang item `owner` có thể invalid.

**11. Nhầm attribute `Requests` với CompositeData item `requests`.**  
Quy tắc tên tại hai tầng khác nhau.

**12. Nghĩ record không được MXBean hỗ trợ.**  
Record mapping hiện hành và canonical constructor có thể tái dựng.

**13. Dùng record rỗng.**  
Theo Java SE 26, record không có components không convertible.

**14. Chỉ kiểm tra chiều Java → CompositeData.**  
Nếu client có typed proxy hoặc operation nhận DTO, còn phải test inverse mapping.

**15. Dùng bean chỉ có getters nhưng không có from/constructor/setters cho vị trí cần reconstruct.**  
Dẫn tới `InvalidObjectException` hoặc wrapped exception.

**16. Coi `@java.beans.ConstructorProperties` là duy nhất.**  
Có `@javax.management.ConstructorParameters` và record canonical constructor; cân nhắc runtime java.desktop.

**17. Đọc `MBeanAttributeInfo.getType()` và tưởng đó luôn là OpenType.**  
Đọc descriptor `JMX.OPEN_TYPE_FIELD`.

**18. So field `mxbean` với Boolean.TRUE.**  
Javadoc quy định đây là String `"true"`.

**19. Dùng arbitrary ChildMXBean object chưa register.**  
MXBean reference cần `ObjectName` trong cùng MBeanServer.

**20. Coi MXBean có thể tự bảo mật remote JMX.**  
MXBean chỉ giải quyết cấu trúc dữ liệu; remote JMX phải có authentication, authorization, TLS và network policy riêng.

**21. Return một Map hoặc CompositeData không giới hạn số lượng rows/items.**  
Có thể gây memory pressure, blocking monitoring và serialization overhead.

**22. Expose secrets qua management getters.**  
Scalar/String/CompositeData vẫn có thể chứa mật khẩu, token và dữ liệu nhạy cảm.

**23. Thay tên field/enum không tính tới clients hiện có.**  
Open Data schema và typed model là contract, cần versioning.

**24. Dùng getters có side effects hoặc thực hiện I/O mạng lâu.**  
Polling monitoring có thể kích hoạt nghiệp vụ hoặc làm chậm application.

**25. Không quan tâm JPMS exports/visibility.**  
Trong named module, converter cần nhìn thấy các public types/accessors/constructors theo quy tắc reflective access.

## 11. Thiết kế MXBean production

### 11.1. Định nghĩa snapshot DTO riêng

Thay vì expose trực tiếp một domain object có database connections, threads, security credentials hoặc cấu trúc phức tạp, hãy đưa ra record nhỏ:

```java
public record CapacitySnapshot(
        long used,
        long capacity,
        long observedAtEpochMillis) {}
```

Đây là snippet, có thể dùng làm return type. Implementation cần chụp values **nhất quán**, không gọi các getters riêng rẽ từ state đang thay đổi mà không đồng bộ.

### 11.2. Giữ schema và units ổn định

Tên `getLatency()` không nêu đơn vị. Nên dùng `getLatencyMillis()` hoặc mô tả thông số rõ. Nếu đổi `state` sang `status` trong record, raw CompositeData item name thay đổi và dashboards gọi `data.get("state")` có thể hỏng.

Với enum, đổi tên constant cũng có thể khiến old client không reconstruct. Khi thay MXBean contract, ghi changelog và kiểm thử backward compatibility.

### 11.3. Quản lý dữ liệu và đồng thời

- Giới hạn số rows/columns/tầng lồng nhau của `TabularData` và `CompositeData`.
- Không return live mutable collection đang bị thread khác thay đổi.
- Dùng immutable snapshots, `List.copyOf` hoặc `Map.copyOf` khi thích hợp.
- Không đưa private key, access token, password hoặc personal data vào getters.
- Không để management operation thực hiện hành động nguy hiểm mà không có authorization/audit.
- Định nghĩa timeout/size limits khi generic monitoring gọi getter tốn CPU hoặc I/O.

### 11.4. JMX remote là một security boundary riêng

Bài thực hành dùng local MBeanServer, không mở port. Nếu dịch vụ thực sự bật remote JMX/RMI:
- Thiết lập authentication/TLS theo deployment policy.
- Ràng buộc network bind và firewall.
- Giới hạn read/write/invoke permissions.
- Audit operations và giảm thông tin lộ qua metadata.
- Không expose remote JMX công khai chỉ vì dùng MXBean.
- Không tự tin mọi ObjectName do client truyền vào là resource được phép điều khiển.

## 12. Sự khác biệt giữa lỗi mapping và lỗi runtime

### 12.1. OpenDataException

Thường là lỗi **Java → OpenType/Open Data**, như một Java type không convertible, getters không hợp lệ hoặc SortedSet có non-null Comparator khi chuyển runtime. Khi register interface không hợp lệ, JMX có thể wrap thành `NotCompliantMBeanException`.

### 12.2. InvalidObjectException

Thường liên quan **Open Data → Java** khi type không reconstructible, một item bắt buộc vắng mặt hoặc enum string không tương ứng với constant. Exceptions có thể được wrap trong `RuntimeMBeanException` hoặc `UndeclaredThrowableException` tùy call path.

Đừng catch tất cả rồi trả giá trị giả. Kiểm tra root cause và xác định chiều chuyển đổi đang thất bại.

### 12.3. MBeanInfo và OpenMBeanInfo

MXBean có Open Types, nhưng `MBeanInfo` được thiết kế để giữ tương thích với MBean tooling; không ép instance sang `OpenMBeanInfo`. Khi cần schema Open Data, lấy descriptor fields `openType`/`originalType`.

## 13. Checklist khi viết và kiểm tra MXBean

- [ ] Interface public, tên kết thúc `MXBean` hoặc gắn `@MXBean` rõ.
- [ ] Có `requires java.management` nếu project là named module.
- [ ] Mọi attribute/operation return và parameters đều có mapping.
- [ ] Parameters reconstructible; typed proxy results reconstructible.
- [ ] Dùng records hoặc DTO getters nhỏ, tránh arbitrary object/recursive graph.
- [ ] Thử raw `getAttribute` với `String[]`, `CompositeData`, `TabularData`.
- [ ] Thử typed `JMX.newMXBeanProxy` để kiểm tra inverse conversion.
- [ ] Nếu custom bean, dùng `from(CompositeData)`/record/`@ConstructorParameters` phù hợp.
- [ ] Không dựa vào thứ tự Set/Map; kiểm tra SortedSet/SortedMap comparator rules.
- [ ] Giữ correct names giữa attributes và composite items.
- [ ] Đọc `JMX.OPEN_TYPE_FIELD` và `JMX.ORIGINAL_TYPE_FIELD`.
- [ ] Không coi `MBeanInfo.mxbean` là boolean Java.
- [ ] Register child MXBeans cùng server nếu cần ObjectName mapping.
- [ ] Giới hạn dữ liệu, timeouts và side effects trong getters.
- [ ] Giữ schema, units và enum constants tương thích.
- [ ] Bảo mật remote JMX separately; không chứa secrets.
- [ ] Test trong đúng JDK/provider/module configuration của sản phẩm.
- [ ] Không dùng API deprecated/removed để giải quyết mapping mới.

## 14. Câu hỏi tự kiểm tra

**1. OpenType là gì?**  
Đối tượng mô tả schema của Open Data, không phải value.

**2. OpenType có mấy subclass chính?**  
Bốn: SimpleType, ArrayType, CompositeType, TabularType.

**3. List<String> raw thành gì?**  
String[] với ArrayType của SimpleType.STRING.

**4. Map<String,Integer> raw thành gì?**  
TabularData có rows key/value, index key.

**5. int[] raw có biến thành Integer[] không?**  
Không, giữ primitive int[].

**6. enum Mode raw thành gì?**  
Tên enum constant dạng String.

**7. record Snapshot raw thành gì?**  
CompositeData theo CompositeType có items tên record components.

**8. Record có cần ConstructorParameters để tái dựng không?**  
Không, canonical constructor có thể được dùng.

**9. JavaBean getCount trở thành item gì?**  
`count` (lowercase) bên trong CompositeData.

**10. MXBean getRequests trở thành attribute gì?**  
`Requests` (uppercase R).

**11. Khi nào type cần reconstructible?**  
Đối với MXBean operation parameters, và return values của typed MXBean proxy.

**12. Static factory cần có chữ ký gì?**  
`public static T from(CompositeData cd)`.

**13. Constructor annotation nằm trong java.management là gì?**  
`@javax.management.ConstructorParameters`.

**14. Tham chiếu ChildMXBean raw thành gì?**  
ObjectName của child đã đăng ký cùng MBeanServer.

**15. Dựa vào MBeanInfo.getType là đủ để biết OpenType?**  
Không, dùng descriptor openType.

**16. Field mxbean trong descriptor có giá trị Boolean.TRUE không?**  
Không, chuỗi `"true"` theo spec.

**17. Vì sao Object getArbitrary không convertible?**  
Object không mang cấu trúc public getter/record schema hợp lệ để chuyển sang Open Type tùy ý.

**18. 63/63 PASS có chứng minh mọi loại Java đều convertible không?**  
Không. Chỉ những type và inverse conversions trong demo trên OpenJDK24.

**19. Dùng MXBean có tự bật remote JMX không?**  
Không. Registration cục bộ và remote connector là hai bước riêng.

**20. MXBean có thay authentication/authorization của JMX không?**  
Không. Nó chỉ quy định data type representation và conversion.

## 15. Tài liệu tham khảo đang áp dụng

- [Oracle Java SE 26 — `javax.management.MXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): đặc tả mapping, records, collections, maps, reconstructibility, reference MXBean, MBeanInfo và exceptions.
- [Oracle Java SE 26 — `OpenType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/OpenType.html): bốn subclass, allowed class names.
- [Oracle Java SE 26 — `SimpleType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/SimpleType.html): scalar Open Types.
- [Oracle Java SE 26 — `ArrayType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/ArrayType.html): primitive/object arrays, dimensions.
- [Oracle Java SE 26 — `CompositeType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeType.html): fields schema.
- [Oracle Java SE 26 — `CompositeData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): raw structured values.
- [Oracle Java SE 26 — `TabularType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularType.html): table schema, index names.
- [Oracle Java SE 26 — `TabularData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularData.html): table values.
- [Oracle Java SE 26 — `JMX`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): typed MXBean proxy và constants của descriptors.
- [Oracle Java SE 26 — `MBeanServer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): registration, getAttribute, invoke.
- [Oracle Java SE 26 — `ConstructorParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/ConstructorParameters.html): immutable DTO reconstruction.
- [Oracle Java SE 26 — `CompositeDataView`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeDataView.html): custom composite conversion.
- [Oracle JMX Guide](https://docs.oracle.com/en/java/javase/25/jmx/java-management-extensions-guide.pdf): tổng quan use cases MXBean.

**Ghi nhớ:** MXBean chỉ cho phép Java types có mapping Open Types được định nghĩa. List → array, Map → TabularData, enum → String, record/JavaBean → CompositeData, MXBean reference → ObjectName. Raw JMX clients dùng các types chuẩn; typed proxy dựng lại Java DTO **khi reconstructible**. Thiết kế monitoring data nhỏ, không đệ quy, có schema ổn định, bảo vệ JMX endpoint và kiểm tra cả raw/typed call paths.
