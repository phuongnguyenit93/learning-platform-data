# MXBean: CompositeData, TabularData và cấu trúc kết quả

## Mục tiêu

Khi đọc dữ liệu quản trị của Java qua JMX, bạn có thể thấy một MXBean có method Java trả về `MemoryUsage`, `record`, `Map<String, Integer>` hoặc `List<String>`, nhưng lời gọi **`MBeanServer.getAttribute(...)`** lại trả về **`CompositeData`**, **`TabularData`** hoặc **mảng**. Điều đó **không phải lỗi cast**: MXBean cố ý chuyển các Java types sang **JMX Open Data Types** để những client không có model classes riêng của ứng dụng vẫn có thể đọc được.

Bài học này trả lời trực tiếp: **`CompositeData`, `TabularData` được tổ chức như thế nào và làm sao đọc, kiểm tra, tạo, chuyển ngược cấu trúc kết quả của MXBean?**

Sau bài học bạn có thể:

1. Phân biệt **Java type**, **OpenType** (schema) và **open-data value** (dữ liệu thực) trong MXBean.
2. Đọc một `CompositeData` bằng `get(String)`/`getAll(String[])`, tìm trường qua `getCompositeType().keySet()`, hiểu `CompositeType.getType(...)`.
3. Đọc một `TabularData` bằng `getTabularType()`, `getIndexNames()`, `getRowType()`, `size()`, `get(Object[])` và `values()`.
4. Hiểu ánh xạ **`Map<K,V> → TabularData`**: bảng gồm các dòng `{key, value}`, mỗi dòng là `CompositeData`, chỉ mục mặc định của map là `key`.
5. Đọc giá trị **lồng nhau**: `Map<String, Snapshot>` trở thành bảng mà trường `value` của một dòng lại là `CompositeData`.
6. Hiểu ánh xạ `record`, Java bean getters, enum, List, Set, arrays và khác biệt giữa OpenData interface với implementation support.
7. So sánh **raw `MBeanServer`** với **typed `JMX.newMXBeanProxy`**: cùng MXBean nhưng hai lớp nhìn khác nhau.
8. Sử dụng `CompositeDataSupport`, `CompositeType`, `TabularDataSupport` và `TabularType` để dựng một Open Data result đúng schema.
9. Bắt lỗi **trường không tồn tại**, **kiểu index sai**, **index trùng lặp** và bảo vệ tương thích schema khi nâng cấp.
10. Đọc một MXBean thật có sẵn trong JVM: `java.lang:type=Memory`, attribute `HeapMemoryUsage`, chuyển `CompositeData` về `MemoryUsage.from(...)`.
11. Chạy một ví dụ Java 17+ **đã biên dịch bằng `javac --release 17` và chạy thật trên OpenJDK 24**, với **50/50 assertions PASS** và stdout chính xác.
12. Biết giới hạn an toàn: local/remote JMX, dữ liệu quản trị nhạy cảm, kích cỡ payload, tính nhất quán của snapshot và version compatibility.

**Special Note:** Chỉ lấy kiến thức còn được dùng hiện nay. `MXBean`, `CompositeData`, `TabularData` và Open MBean types nằm trong module **`java.management`**, vẫn được Oracle Java SE/JDK 26 ghi nhận. Ví dụ sử dụng **Java 17+ records**, `JMX.newMXBeanProxy` và phương pháp hiện hành; không sử dụng các API nội bộ `sun.*`, không khuyên bật JMX remote không xác thực và không dựa vào ví dụ legacy cần Java serialization model classes để đọc kết quả.

## 1. Tại sao MXBean chuyển Java objects sang Open Data?

Một Standard MBean có thể yêu cầu client biết một Java class riêng do ứng dụng định nghĩa để giải mã kết quả. MXBean tạo ra một **hợp đồng quản trị ít phụ thuộc model classes hơn**: qua JMX layer, các giá trị được ánh xạ sang những kiểu mở chuẩn được thư viện Java cung cấp.

```text
Ứng dụng Java                         MBeanServer / JMX                 Client
-----------------                    -----------------                 ----------------
record Snapshot(...)                  CompositeData                     Generic JMX viewer
Map<String,Integer>                   TabularData                       Script đọc Open Data
List<String>                          String[]                          Remote JMX connector
State.READY                           "READY"
        |                                  ^
        +----- MXBean type mapping -------+
                                           \
                                            +---- JMX.newMXBeanProxy(...) ---->
                                                  Snapshot / Map / List / State
                                                  (đã chuyển ngược)
```

Đây là sơ đồ khái niệm của **mappings**, không nói rằng tất cả JMX tools đều bắt buộc hỗ trợ mọi Java class riêng của ứng dụng. Client dùng **raw Open Data** không cần biết `Snapshot` class; client dùng **typed MXBean proxy** lại phải có interface và các kiểu Java được proxy khai báo nếu muốn nhận về đúng types.

`CompositeData` và `TabularData` là **interfaces của Open MBean**. Chúng mô tả dữ liệu quản trị, **không** phải JSON/BSON/SQL mặc định. Không giả định JMX sẽ tự serialize mọi object tùy ý hoặc chuyển nguyên map thành một `java.util.Map` tại lớp raw.

### 1.1. Ba tầng của một giá trị MXBean

| Tầng | Ví dụ | Công dụng |
| --- | --- | --- |
| Khai báo Java | `Snapshot getSnapshot()` | API mà code ứng dụng/proxy muốn dùng |
| OpenType schema | `CompositeType` có các items `service`, `requests`, `healthy` | Diễn tả tên trường và kiểu hợp lệ, client tự khám phá |
| Open-data value | `CompositeData` có `service="rental"`, `requests=14L`, `healthy=true` | Giá trị thực được `getAttribute` trả về |
| Typed proxy result | `new Snapshot("rental",14L,true)` | Kết quả sau khi MXBean proxy tái dựng Java type |

Đừng nhầm **`CompositeType`** (schema) với **`CompositeData`** (value). Tương tự, **`TabularType`** mô tả dạng bảng, còn **`TabularData`** giữ các rows.

### 1.2. Cấu trúc kết quả có thể lồng nhau

```text
CompositeData("Snapshot")
  CompositeType
    healthy   -> SimpleType.BOOLEAN
    requests  -> SimpleType.LONG
    service   -> SimpleType.STRING
  Values
    healthy   -> true
    requests  -> 14L
    service   -> "rental"

TabularData("Map<String,Integer>")
  TabularType
    rowType: CompositeType(key:String, value:Integer)
    indexNames: ["key"]
  Rows:
    {key="ok",     value=12}
    {key="errors", value=2}
```

Tập item names của `CompositeType.keySet()` là một tập tên. Bài không dựa vào thứ tự khi lấy danh sách trường; nếu muốn hiển thị có thứ tự, ứng dụng phải chọn và sắp xếp thứ tự rõ ràng.

## 2. Các classes Open MBean quan trọng

| Loại | Lớp/interface | Câu hỏi nó trả lời |
| --- | --- | --- |
| Base schema | `OpenType<?>` | Giá trị open type có kiểu gì? |
| Scalar schema | `SimpleType.STRING`, `INTEGER`, `LONG`, `BOOLEAN` | Một giá trị đơn giản thuộc kiểu nào? |
| Array schema | `ArrayType<?>` | Mảng mấy chiều, element OpenType nào? |
| Composite schema | `CompositeType` | Có những item names/types nào? |
| Composite value | `CompositeData` | Item này đang mang giá trị gì? |
| Composite implementation | `CompositeDataSupport` | Tạo một CompositeData từ schema + values |
| Table schema | `TabularType` | RowType là gì, indexNames nào làm khóa? |
| Table value | `TabularData` | Các rows và cách lookup theo index |
| Table implementation | `TabularDataSupport` | Bảng hỗ trợ `put/get/size`, kiểm tra row/index |
| JMX proxy | `JMX.newMXBeanProxy` | Chuyển Open Data ↔ kiểu Java của interface |
| Server metadata | `MBeanInfo`, `MBeanAttributeInfo` | Attribute/operation names/types công bố qua JMX |
| Built-in MXBeans | `MemoryMXBean`, `ThreadMXBean`, ... | Dữ liệu JVM thật, có thể inspect qua JMX |

Tất cả các lớp JMX trên có trong **module `java.management`**. Dùng Java 17+ không cần cài thêm thư viện hoặc truy cập `com.sun.*` nội bộ để làm việc với Open MBean data. Java platform MXBeans có thể sử dụng thêm implementation-specific extensions, nhưng phần này chỉ dựa trên APIs công khai hiện hành.

## 3. MXBean mapping rules: Java type thành OpenType nào?

Oracle Javadoc `javax.management.MXBean` có bảng quy tắc ánh xạ type đầy đủ. Những quy tắc thiết yếu:

| Java type của MXBean | OpenType / open data | Điểm cần nhớ |
| --- | --- | --- |
| `int` / `Integer` | `SimpleType.INTEGER` / `Integer` | Java primitive được boxing ở JMX object layer |
| `long` / `Long` | `SimpleType.LONG` / `Long` | Kiểm tra kiểu `Long`, không ép sang `Integer` |
| `boolean` / `Boolean` | `SimpleType.BOOLEAN` / `Boolean` | Boolean là giá trị open |
| `String` | `SimpleType.STRING` / `String` | Không cần cấu trúc phức hợp |
| `ObjectName` | `SimpleType.OBJECTNAME` / `ObjectName` | Chuẩn JMX name |
| `enum State` | `SimpleType.STRING` / `String` | `State.READY` thành `"READY"` |
| `String[]` | `ArrayType` / `String[]` | Array mapping |
| `List<String>` | `ArrayType` / `String[]` | Collection map sang mảng, không phải raw `List` |
| `Set<E>`, `SortedSet<E>` | `ArrayType` / mảng | Có ràng buộc và semantic order riêng |
| `record Snapshot(...)` | `CompositeType` / `CompositeData` | Item names theo record components |
| Java class có getters phù hợp | `CompositeType` / `CompositeData` | Tất cả getters liên quan phải chuyển đổi được |
| `Map<String,Integer>` | `TabularType` / `TabularData` | Mỗi entry là CompositeData `{key,value}` |
| `Map<String,Snapshot>` | `TabularType` / `TabularData` lồng CompositeData | Trường `value` là composite |
| `Snapshot[]` | `ArrayType` / `CompositeData[]` | Mỗi phần tử map sang composite |
| Một MXBean interface khác | `SimpleType.OBJECTNAME` / `ObjectName` | Ánh xạ tham chiếu đến MXBean đã đăng ký |

**Không** có một mapping mặc định cho mọi kiểu `Object`, object graph vòng tròn, stream, socket, thread hoặc các generic collections không xác định được OpenType. Đối với collection, cần generic element/key/value types có khả năng ánh xạ. Nếu không convertible, đăng ký MXBean hoặc gọi mapping có thể thất bại.

### 3.1. Map được biến thành bảng theo một quy tắc rất cụ thể

Đối với `Map<K,V>`, MXBean spec xác định row type có **đúng hai items** `key` và `value`. Mỗi item có OpenType lần lượt là `opentype(K)` và `opentype(V)`. **IndexNames là `["key"]`** — nó là unique key của bảng.

```text
Map<String,Integer>
  "ok"     -> 12
  "errors" ->  2
           |
           v
TabularType(rowType = CompositeType(key:String,value:Integer),
            indexNames = ["key"])
           |
           v
TabularData rows:
  CompositeData{key="ok",value=12}
  CompositeData{key="errors",value=2}
```

Đây là mapping của **MXBean Map**. Khi bạn tự tạo một `TabularType` bằng constructor, index names **không nhất thiết** phải là `key`; bạn được định nghĩa một hoặc nhiều item names làm index phù hợp schema.

### 3.2. Records được mapping mà không cần JavaBeans getters

Một Java record:

```java
public record Snapshot(String service, long requests, boolean healthy) {}
```

có record components `service`, `requests`, `healthy`, nên OpenType chứa ba items đó với `SimpleType.STRING`, `SimpleType.LONG`, `SimpleType.BOOLEAN`. Java 17+ có records và Oracle Java SE 26 MXBean spec cho phép mapping records mà không cần `@ConstructorParameters` trên canonical constructor. Khi proxy chuyển từ `CompositeData` về `Snapshot`, record canonical constructor được gọi nếu tất cả fields cần thiết hiện diện.

Đừng dùng code JavaBean `getService()` chỉ vì từng ví dụ cũ không biết records. Tuy nhiên không phải mọi record đều convertible: components của nó phải có OpenType hợp lệ, và record rỗng không convertible theo MXBean spec.

### 3.3. JavaBeans-style classes vẫn được hỗ trợ

Một class thông thường có public getter `getOwner()` sẽ có item name `owner` trong `CompositeType`, bắt đầu bằng chữ thường theo quy tắc MXBean mapping. Nếu client cần chuyển ngược từ CompositeData thành object, class phải **reconstructible**: có thể dùng static `from(CompositeData)`, public constructor có `@javax.management.ConstructorParameters`, hoặc public no-args constructor và setter cho các getters phù hợp. Các đường reconstruct khác được Javadoc định nghĩa.

**Không** suy rằng class có getters là luôn có thể chuyển ngược qua typed proxy: convert *Java object → CompositeData* và reconstruct *CompositeData → Java object* là hai hướng khác nhau. Với bài Java 17+ này, dùng record để demonstrable round-trip rõ ràng.

### 3.4. Collection mapping không bảo toàn tùy ý implementation

`List<E>` được ánh xạ thành OpenData array tương ứng; typed proxy có thể reconstruct thành `ArrayList<E>` theo spec. `Map<K,V>` thường trở thành `HashMap<K,V>` khi chuyển ngược; `SortedMap` có ràng buộc Comparable/comparator. Đừng assert một `LinkedHashMap` vẫn giữ insertion order sau JMX mapping hoặc một `List.of(...)` vẫn bất biến về tính mutable.

Bài runnable kiểm tra **nội dung** và **đúng kiểu**, không gắn kết quả test với thứ tự iterate của `Map` hay `TabularData`.

## 4. Đọc CompositeData và kiểm tra CompositeType

### 4.1. API cơ bản

`CompositeData` có `getCompositeType()`, `get(String)`, `getAll(String[])`, `containsKey(String)`, `containsValue(Object)` và `values()`. Một hướng đọc an toàn:

```java
CompositeData data =
        (CompositeData) mbeanServer.getAttribute(name, "Snapshot");

CompositeType type = data.getCompositeType();
for (String item : type.keySet()) {
    OpenType<?> itemType = type.getType(item);
    Object value = data.get(item);
    System.out.println(item + ": " + itemType.getTypeName() + " = " + value);
}
```

Đây là **snippet tích hợp**, cần `MBeanServer mbeanServer`, `ObjectName name`, các imports và MXBean có attribute Snapshot. Nó đọc schema **từ kết quả thực**, không mặc định tất cả versions có đúng ba field.

### 4.2. Dùng item names, không dùng positional array mù

`getAll(new String[] {"requests","service"})` trả values **cùng thứ tự tên truyền vào**. Nếu code thực cần tạo DTO, dùng tên item cụ thể:

```java
if (data.containsKey("requests")
        && data.getCompositeType().getType("requests").equals(SimpleType.LONG)) {
    long requests = (Long) data.get("requests");
}
```

Đây là snippet. `(Long)` là kiểu của `SimpleType.LONG`, không phải primitive Java reflection. Nếu field không tồn tại, `get("missing")` ném **`InvalidKeyException`**; còn `containsKey("missing")` trả `false`. `get(null)` và `get("")` không phải lookups hợp lệ.

### 4.3. Cần phân biệt hai đối tượng Type và Data

- `CompositeType.keySet()`: danh sách item names **theo schema**.
- `CompositeType.getType("requests")`: OpenType của item.
- `CompositeType.isValue(data)`: kiểm tra data là một giá trị hợp lệ theo type.
- `CompositeData.get("requests")`: lấy giá trị thực.
- `CompositeData.containsKey("requests")`: item có được định nghĩa trong data?
- `CompositeData.getAll(String[])`: đọc nhiều items đúng thứ tự do bạn chọn.

Một số triển khai có thể trả items có cấu trúc nested `CompositeData` hoặc `TabularData`. Đừng gọi `toString()` rồi parse bằng regex để lấy field; hãy truy cập schema và typed values.

### 4.4. Ví dụ có sẵn trong JVM: HeapMemoryUsage

`MemoryMXBean.getHeapMemoryUsage()` trả Java `MemoryUsage`. Qua raw JMX `MBeanServer.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")`, kết quả là `CompositeData`. Các fields chuẩn của `MemoryUsage` là `init`, `used`, `committed`, `max`.

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
ObjectName memoryName =
        new ObjectName(ManagementFactory.MEMORY_MXBEAN_NAME);
CompositeData heap = (CompositeData)
        platform.getAttribute(memoryName, "HeapMemoryUsage");

long usedBytes = (Long) heap.get("used");
MemoryUsage usage = MemoryUsage.from(heap);
System.out.println(usage.getUsed() == usedBytes);
```

Đây là snippet có imports. Giá trị bytes là **động**, không thể đưa stdout số bytes cố định cho mọi JVM; chỉ assert `used ≥ 0`, `committed ≥ used` trong ví dụ hoàn chỉnh.

### 4.5. Snapshot nhất quán không đến từ OpenType

Một CompositeData có thể đại diện **một lần gọi getter** của ứng dụng, giúp gom nhiều số đo cùng response. Nhưng MXBean mapping **không tự thêm transaction hay atomic snapshot**. Nếu getter đọc nhiều counters không đồng bộ, các giá trị vẫn có thể không nhất quán. Bạn phải tự thiết kế snapshot object/getter sử dụng cơ chế đồng bộ hoặc cơ chế lấy mẫu phù hợp.

## 5. Đọc TabularData: rows, index và lookup

### 5.1. Phân biệt TabularType và TabularData

`TabularType` chứa **row type** là `CompositeType` và **index names** là danh sách items của row dùng làm khóa. `TabularData` chứa nhiều rows; mỗi row là `CompositeData`.

```java
TabularData table =
        (TabularData) mbeanServer.getAttribute(name, "Counters");

TabularType schema = table.getTabularType();
CompositeType rowType = schema.getRowType();
System.out.println(schema.getIndexNames());
System.out.println(rowType.keySet());
System.out.println(table.size());
```

Đây là snippet có context. Với `Map<String,Integer>`, `schema.getIndexNames()` là list chứa `"key"`, còn `rowType.keySet()` chứa `"key"` và `"value"`.

### 5.2. Lookup theo index là Object[] — không phải String trực tiếp

`TabularData.get(Object[] key)` yêu cầu **mảng key values**, mỗi phần tử tương ứng một index name, đúng kiểu OpenType. Với bảng Map:

```java
CompositeData row = table.get(new Object[]{"ok"});
if (row != null) {
    String key = (String) row.get("key");
    Integer value = (Integer) row.get("value");
}
```

Đây là snippet. Nếu không có index `"ok"`, `get(new Object[]{"missing"})` trả `null`. Nếu key **sai type**, ví dụ `new Object[]{123}` khi cần `String`, `get` có thể ném `InvalidKeyException` theo contract; không mặc định mọi input invalid đều tương đương không tìm thấy.

### 5.3. IndexNames không phải thứ tự hàng

- `table.getTabularType().getIndexNames()` nói **dòng được định danh bằng trường nào**.
- `table.keySet()` là **tập các index values**, theo Javadoc biểu diễn set chứa lists; đừng cast mỗi key thành `Object[]`.
- `table.values()` là tập các `CompositeData` rows; thứ tự iteration **không là API contract để xử lý business**.
- `table.calculateIndex(row)` trả `Object[]` chỉ mục tính từ row.
- `table.containsKey(Object[])` kiểm tra có row với index đó không.
- `table.size()` trả số rows.

Không dùng `table.toString()` để làm một protocol. Đối với tabular results quan trọng, đọc schema và dùng index lookup trực tiếp; nếu cần output ổn định, gom rows thành data structure có explicit sort.

### 5.4. Nested TabularData: Map có value là record

`Map<String,Snapshot>` thành `TabularData`; mỗi row có `key:String` và `value:CompositeData`. Đọc một phần tử:

```java
TabularData byService =
        (TabularData) mbeanServer.getAttribute(name, "ByService");
CompositeData jobsRow = byService.get(new Object[]{"jobs"});
CompositeData jobs = (CompositeData) jobsRow.get("value");

String service = (String) jobs.get("service");
long requests = (Long) jobs.get("requests");
boolean healthy = (Boolean) jobs.get("healthy");
```

Đây là snippet. Không cast trực tiếp `jobsRow.get("value")` thành Java `Snapshot` khi đọc qua raw JMX; muốn Java record cần typed proxy hoặc conversion phù hợp.

### 5.5. Lỗi trùng index và thiếu schema phù hợp

`TabularDataSupport.put(row)` kiểm tra row type và unique index. Nếu đã tồn tại index và thêm row mới/giống row cũ, ném **`KeyAlreadyExistsException`**. Nếu row không conform với `TabularType`, có thể ném **`InvalidOpenTypeException`**. Không thay assumption “TabularData là HashMap nên put cùng key sẽ override”: đối với `TabularDataSupport.put`, duplicate index **bị từ chối**.

### 5.6. Table không mặc định hỗ trợ pagination

TabularData là cấu trúc dữ liệu mở trong một JMX result. JMX getter trả toàn bộ table có thể lớn và tốn heap/network/time khi remote. Với số liệu lớn, thiết kế bounded/filtered methods hoặc một API metrics riêng; đừng giả định TabularData là SQL cursor có pagination.

## 6. Khác biệt raw MBeanServer và typed MXBean proxy

### 6.1. Raw JMX client

`MBeanServer` hoặc `MBeanServerConnection` thấy **Open Data**:

```java
Object rawSnapshot = server.getAttribute(name, "Snapshot");
Object rawCounters = server.getAttribute(name, "Counters");

CompositeData snapshot = (CompositeData) rawSnapshot;
TabularData counters = (TabularData) rawCounters;
```

Các snippets trên cần `server`, `name` hợp lệ. Đây là cách sử dụng cho generic JMX clients, monitoring consoles, scripts và remote viewers không có `Snapshot.class`.

### 6.2. Typed proxy khôi phục Java types

```java
DashboardMXBean proxy =
        JMX.newMXBeanProxy(server, name, DashboardMXBean.class);

Snapshot snapshot = proxy.getSnapshot();
Map<String, Integer> counters = proxy.getCounters();
```

Đây là snippet với `DashboardMXBean` từ ví dụ hoàn chỉnh. **Proxy không trả raw CompositeData ở đây** vì nó tự chuyển theo MXBean mapping và cần biết typed interface/model classes. Đối với record, proxy dùng canonical constructor để tái dựng; với Map/List/enum, thực hiện mapping ngược theo spec.

### 6.3. Raw invoke nhận các OpenData argument types

Khi interface có operation `Snapshot echo(Snapshot input)`, lời gọi proxy `proxy.echo(new Snapshot(...))` tự chuyển input/output thành Open Data. Với raw server API:

```java
CompositeData answer = (CompositeData) server.invoke(
    name, "echo",
    new Object[]{snapshot},
    new String[]{CompositeData.class.getName()});
```

Đây là snippet cần `server`, `name` và `CompositeData snapshot`; signature **phải phù hợp kiểu Open Data** của operation, không suy rằng `Snapshot.class.getName()` sẽ khớp raw MXBean operation. Ví dụ runnable đã thực sự chạy cả raw invoke và typed proxy.

### 6.4. MBeanInfo dùng để biết kết quả raw là kiểu gì

`server.getMBeanInfo(name)` trả metadata các attributes/operations. Với `Snapshot`/`Counters`, raw attribute types lần lượt là `javax.management.openmbean.CompositeData` và `javax.management.openmbean.TabularData`. Các descriptors từ Open MBean có thể mang thông tin `openType`, `originalType`; client production nên inspect metadata được cung cấp thay vì đoán từ tên getter.

```java
MBeanInfo info = server.getMBeanInfo(name);
for (var attribute : info.getAttributes()) {
    System.out.println(attribute.getName() + ": " + attribute.getType());
}
```

Đây là snippet. Đối với generic client, tên field và type contract quan trọng hơn việc dự đoán class gốc ở server.

## 7. Tự tạo CompositeDataSupport và TabularDataSupport

Bạn không bắt buộc dùng MXBean automatic mapping để tạo Open Data. Các lớp support cho phép xây dựng có kiểm tra type/schema.

### 7.1. Định nghĩa CompositeType

```java
CompositeType rowType = new CompositeType(
    "MetricRow", "MetricRow",
    new String[]{"name", "count"},
    new String[]{"Metric name", "Metric count"},
    new OpenType<?>[]{SimpleType.STRING, SimpleType.INTEGER}
);
```

`typeName` là định danh schema, `description` mô tả, `itemNames` là tên trường, `itemDescriptions` là giải thích và `itemTypes` phải tương ứng. Một `CompositeType` không giữ dữ liệu cụ thể.

### 7.2. Tạo CompositeDataSupport

```java
CompositeDataSupport row = new CompositeDataSupport(
    rowType,
    new String[]{"name", "count"},
    new Object[]{"alpha", 4}
);
```

Đây là giá trị có `name="alpha"`, `count=Integer(4)`. Constructor kiểm tra tên và giá trị phù hợp CompositeType; nếu thiếu item bắt buộc hoặc sai kiểu, sẽ thất bại. Một `CompositeDataSupport` không phải Java `record Snapshot`: nó là dạng Open Data để tool khác đọc mà không có model class.

### 7.3. Định nghĩa TabularType và tạo bảng

```java
TabularType tableType = new TabularType(
    "MetricTable", "MetricTable", rowType,
    new String[]{"name"}
);
TabularDataSupport table = new TabularDataSupport(tableType);
table.put(row);
CompositeData selected = table.get(new Object[]{"alpha"});
```

Ví dụ này dùng `name` làm index thay vì `key`, vì ta **tự định nghĩa** TabularType. Với MXBean `Map<K,V>`, index mặc định vẫn là `key`. Sau khi put, `table.get(new Object[]{"alpha"})` trả row. `table.put(row)` lần hai cùng index sẽ ném KeyAlreadyExistsException.

### 7.4. Khi nào nên tạo bằng tay?

- Viết custom Open MBean/DynamicMBean trả metadata schema rõ ràng.
- Tạo một Open Data response từ hệ thống monitoring không có model class tương ứng.
- Test type-validation, duplicate indices hoặc hướng tiêu thụ dữ liệu của generic JMX clients.
- Chuyển dữ liệu thủ công theo một schema đã biết từ JMX connector.

Nếu bạn chỉ đang expose Java application objects phù hợp MXBean mapping, thường nên để MXBean tự chuyển và test qua raw MBeanServer. Không tự build CompositeData bằng tay nếu nó chỉ làm code dài mà không mang thêm lợi ích.

## 8. Chương trình Java 17+ hoàn chỉnh và đã chạy thật

### 8.1. Kịch bản test

Bài cung cấp **một file `MxBeanOpenDataDemo.java`** chạy bằng JDK 17+ mà không cần Maven/Spring, external libraries, server JMX remote hay Internet.

- Tạo `MBeanServerFactory.newMBeanServer()` — MBeanServer **cục bộ**, không mở network port.
- Định nghĩa `DashboardMXBean` với `Snapshot` là Java `record`, `Map<String,Integer>`, `Map<String,Snapshot>`, `List<String>`, `Snapshot[]` và `enum State`.
- Đăng ký bằng `ObjectName("demo.mxbean:type=Dashboard")` rồi đọc raw JMX Open Data.
- Kiểm tra CompositeType item names/types và values; false/missing item conditions.
- Kiểm tra TabularType row schema, index by key, lookup by `Object[]{"ok"}` và nested CompositeData values.
- Dùng JMX.newMXBeanProxy để khôi phục Java record, Map, List, array, enum; gọi operation `echo` qua proxy và raw invoke.
- Kiểm tra MBeanInfo raw attribute types.
- Dựng CompositeDataSupport/TabularDataSupport thủ công, thử duplicate index và wrong key type.
- Đọc MemoryMXBean `HeapMemoryUsage` thật từ JVM qua platform MBeanServer và `MemoryUsage.from(...)`.
- Unregister MBean sau test, không để MBean đăng ký lại vô tình.

**Không hardcode lượng heap hiện tại** vì JVM memory luôn thay đổi. Chỉ assert những invariants của MemoryUsage. Những số `rental=14` và `ok=12/errors=2` do chính code fixture tạo, nên stdout của chúng là cố định.

### 8.2. Toàn bộ `MxBeanOpenDataDemo.java`

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.management.JMX;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.InvalidKeyException;
import javax.management.openmbean.KeyAlreadyExistsException;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;
import javax.management.openmbean.TabularData;
import javax.management.openmbean.TabularDataSupport;
import javax.management.openmbean.TabularType;

public final class MxBeanOpenDataDemo {
    public enum State { READY, PAUSED }

    public record Snapshot(String service, long requests, boolean healthy) {}

    public interface DashboardMXBean {
        Snapshot getSnapshot();
        Map<String, Integer> getCounters();
        Map<String, Snapshot> getByService();
        List<String> getOwners();
        Snapshot[] getHistory();
        State getState();
        Snapshot echo(Snapshot input);
    }

    public static final class Dashboard implements DashboardMXBean {
        @Override
        public Snapshot getSnapshot() {
            return new Snapshot("rental", 14L, true);
        }

        @Override
        public Map<String, Integer> getCounters() {
            Map<String, Integer> counters = new LinkedHashMap<>();
            counters.put("ok", 12);
            counters.put("errors", 2);
            return counters;
        }

        @Override
        public Map<String, Snapshot> getByService() {
            Map<String, Snapshot> metrics = new LinkedHashMap<>();
            metrics.put("api", new Snapshot("api", 9L, true));
            metrics.put("jobs", new Snapshot("jobs", 5L, false));
            return metrics;
        }

        @Override
        public List<String> getOwners() {
            return List.of("An", "Binh");
        }

        @Override
        public Snapshot[] getHistory() {
            return new Snapshot[] {
                new Snapshot("api", 9L, true),
                new Snapshot("jobs", 5L, false)
            };
        }

        @Override
        public State getState() {
            return State.READY;
        }

        @Override
        public Snapshot echo(Snapshot input) {
            return input;
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        ObjectName name = new ObjectName("demo.mxbean:type=Dashboard");
        check("interfaceRecognized", JMX.isMXBeanInterface(DashboardMXBean.class));
        server.registerMBean(new Dashboard(), name);
        try {
            check("registered", server.isRegistered(name));

            Object rawSnapshot = server.getAttribute(name, "Snapshot");
            check("rawSnapshotIsComposite", rawSnapshot instanceof CompositeData);
            CompositeData snapshot = (CompositeData) rawSnapshot;
            CompositeType snapshotType = snapshot.getCompositeType();
            check("recordItems", snapshotType.keySet().containsAll(
                    List.of("service", "requests", "healthy"))
                    && snapshotType.keySet().size() == 3);
            check("recordOpenTypes",
                    SimpleType.STRING.equals(snapshotType.getType("service"))
                    && SimpleType.LONG.equals(snapshotType.getType("requests"))
                    && SimpleType.BOOLEAN.equals(snapshotType.getType("healthy")));
            check("recordValues",
                    "rental".equals(snapshot.get("service"))
                    && Long.valueOf(14L).equals(snapshot.get("requests"))
                    && Boolean.TRUE.equals(snapshot.get("healthy")));
            check("compositeTypeAcceptsValue", snapshotType.isValue(snapshot));
            check("compositeKeyPresent", snapshot.containsKey("service"));
            check("compositeMissingKeyFalse", !snapshot.containsKey("missing"));
            check("compositeGetAllOrder",
                    Arrays.equals(snapshot.getAll(new String[]{"requests", "service"}),
                            new Object[]{14L, "rental"}));
            boolean invalidItem = false;
            try {
                snapshot.get("missing");
            } catch (InvalidKeyException expected) {
                invalidItem = true;
            }
            check("compositeInvalidKeyRejected", invalidItem);

            Object rawMap = server.getAttribute(name, "Counters");
            check("rawMapIsTabular", rawMap instanceof TabularData);
            TabularData counters = (TabularData) rawMap;
            TabularType tableType = counters.getTabularType();
            check("mapIndexByKey", tableType.getIndexNames().equals(List.of("key")));
            check("mapRowNames", tableType.getRowType().keySet()
                    .equals(java.util.Set.of("key", "value")));
            check("mapRowTypes",
                    SimpleType.STRING.equals(tableType.getRowType().getType("key"))
                    && SimpleType.INTEGER.equals(tableType.getRowType().getType("value")));
            check("mapRowCount", counters.size() == 2);
            check("mapContainsIndex", counters.containsKey(new Object[]{"ok"}));
            check("mapIndexLookup",
                    "ok".equals(counters.get(new Object[]{"ok"}).get("key"))
                    && Integer.valueOf(12).equals(
                            counters.get(new Object[]{"ok"}).get("value")));
            check("mapMissingKey", counters.get(new Object[]{"unknown"}) == null);
            check("mapNoOrderAssumed", counters.keySet().size() == 2);
            check("tabularTypeAcceptsValue", tableType.isValue(counters));

            TabularData byService = (TabularData) server.getAttribute(name, "ByService");
            check("nestedMapIsTabular", byService.size() == 2
                    && byService.getTabularType().getIndexNames().equals(List.of("key")));
            CompositeData nestedRow = byService.get(new Object[]{"jobs"});
            check("nestedValueIsComposite", nestedRow.get("value") instanceof CompositeData);
            CompositeData nested = (CompositeData) nestedRow.get("value");
            check("nestedRecordFields", "jobs".equals(nested.get("service"))
                    && Long.valueOf(5L).equals(nested.get("requests"))
                    && Boolean.FALSE.equals(nested.get("healthy")));

            Object ownersRaw = server.getAttribute(name, "Owners");
            check("listMappedToArray", ownersRaw instanceof String[]
                    && Arrays.equals((String[]) ownersRaw,
                            new String[]{"An", "Binh"}));
            Object historyRaw = server.getAttribute(name, "History");
            check("recordArrayMapped", historyRaw instanceof CompositeData[]
                    && ((CompositeData[]) historyRaw).length == 2);
            check("enumMappedToString",
                    "READY".equals(server.getAttribute(name, "State")));

            DashboardMXBean proxy = JMX.newMXBeanProxy(
                    server, name, DashboardMXBean.class);
            check("proxyRecordRestored",
                    proxy.getSnapshot().equals(new Snapshot("rental", 14L, true)));
            check("proxyMapRestored", proxy.getCounters().equals(
                    Map.of("ok", 12, "errors", 2)));
            check("proxyNestedMapRestored",
                    proxy.getByService().get("jobs").equals(
                            new Snapshot("jobs", 5L, false)));
            check("proxyListRestored", proxy.getOwners().equals(
                    List.of("An", "Binh")));
            check("proxyArrayRestored", Arrays.equals(
                    proxy.getHistory(),
                    new Snapshot[]{
                        new Snapshot("api", 9L, true),
                        new Snapshot("jobs", 5L, false)
                    }));
            check("proxyEnumRestored", proxy.getState() == State.READY);

            Snapshot input = new Snapshot("worker", 3L, false);
            check("proxyOperationRoundTrip", proxy.echo(input).equals(input));
            Object rawEcho = server.invoke(name, "echo",
                    new Object[]{snapshot}, new String[]{CompositeData.class.getName()});
            check("rawOperationReturnsComposite", rawEcho instanceof CompositeData);
            check("rawOperationValue",
                    "rental".equals(((CompositeData) rawEcho).get("service")));

            MBeanInfo info = server.getMBeanInfo(name);
            check("metadataListsCompositeAttribute",
                    Arrays.stream(info.getAttributes()).anyMatch(a ->
                            a.getName().equals("Snapshot")
                            && a.getType().equals(CompositeData.class.getName())));
            check("metadataListsTabularAttribute",
                    Arrays.stream(info.getAttributes()).anyMatch(a ->
                            a.getName().equals("Counters")
                            && a.getType().equals(TabularData.class.getName())));

            CompositeType manualRowType = new CompositeType(
                    "MetricRow", "MetricRow",
                    new String[]{"name", "count"},
                    new String[]{"Metric name", "Metric count"},
                    new OpenType<?>[]{SimpleType.STRING, SimpleType.INTEGER});
            CompositeDataSupport manualRow = new CompositeDataSupport(
                    manualRowType, new String[]{"name", "count"},
                    new Object[]{"alpha", 4});
            check("manualCompositeBuilt",
                    "alpha".equals(manualRow.get("name"))
                    && Integer.valueOf(4).equals(manualRow.get("count")));
            check("manualSchemaAcceptsRow", manualRowType.isValue(manualRow));
            TabularType manualTableType = new TabularType(
                    "MetricTable", "MetricTable", manualRowType,
                    new String[]{"name"});
            TabularDataSupport manualTable = new TabularDataSupport(manualTableType);
            manualTable.put(manualRow);
            check("manualTabularBuilt",
                    manualTable.size() == 1
                    && manualTableType.isValue(manualTable));
            check("manualIndexCalculation",
                    Arrays.equals(manualTable.calculateIndex(manualRow),
                            new Object[]{"alpha"}));
            check("manualIndexLookup",
                    manualRow.equals(manualTable.get(new Object[]{"alpha"})));
            boolean duplicateRejected = false;
            try {
                manualTable.put(manualRow);
            } catch (KeyAlreadyExistsException expected) {
                duplicateRejected = true;
            }
            check("duplicateIndexRejected", duplicateRejected);
            boolean wrongIndexRejected = false;
            try {
                manualTable.get(new Object[]{123});
            } catch (InvalidKeyException expected) {
                wrongIndexRejected = true;
            }
            check("wrongIndexTypeRejected", wrongIndexRejected);

            MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
            ObjectName memoryName = new ObjectName(
                    ManagementFactory.MEMORY_MXBEAN_NAME);
            Object memoryRaw = platform.getAttribute(
                    memoryName, "HeapMemoryUsage");
            check("platformMemoryIsComposite",
                    memoryRaw instanceof CompositeData);
            CompositeData memory = (CompositeData) memoryRaw;
            check("platformMemoryItems",
                    memory.getCompositeType().keySet()
                            .containsAll(List.of("init", "used", "committed", "max")));
            MemoryUsage memoryUsage = MemoryUsage.from(memory);
            check("platformMemoryFromWorks", memoryUsage != null
                    && memoryUsage.getUsed() >= 0
                    && memoryUsage.getCommitted() >= memoryUsage.getUsed());
            MemoryMXBean memoryProxy = JMX.newMXBeanProxy(
                    platform, memoryName, MemoryMXBean.class);
            check("platformTypedProxyWorks",
                    memoryProxy.getHeapMemoryUsage() instanceof MemoryUsage);

            System.out.println("snapshot=" + proxy.getSnapshot().service()
                    + "," + proxy.getSnapshot().requests());
            System.out.println("counters=" + proxy.getCounters().get("ok")
                    + "," + proxy.getCounters().get("errors"));
            System.out.println("manualRow=" + manualTable.get(new Object[]{"alpha"}).get("name")
                    + "," + manualTable.get(new Object[]{"alpha"}).get("count"));
        } finally {
            server.unregisterMBean(name);
            check("unregistered", !server.isRegistered(name));
        }
    }
}
```

### 8.3. Biên dịch và chạy

Đặt toàn bộ code vào file `MxBeanOpenDataDemo.java` (tên file khớp public class) và dùng JDK 17+:

```bash
javac --release 17 MxBeanOpenDataDemo.java
java MxBeanOpenDataDemo
```

File không cần JavaBean library riêng, không cần build tool/framework. `java.management` thuộc Java SE. Nếu project dùng named modules, một module-info tối thiểu có:

```java
module demo.mxbean {
    requires java.management;
}
```

Đây là **snippet trong file `module-info.java` riêng**, không đặt cùng `MxBeanOpenDataDemo.java` ở trên. Khi đóng gói runtime tùy chỉnh bằng `jlink`, bảo đảm image chứa module `java.management` và những phụ thuộc hợp lệ.

### 8.4. Stdout chính xác từ test trên OpenJDK 24

```text
interfaceRecognized=true
registered=true
rawSnapshotIsComposite=true
recordItems=true
recordOpenTypes=true
recordValues=true
compositeTypeAcceptsValue=true
compositeKeyPresent=true
compositeMissingKeyFalse=true
compositeGetAllOrder=true
compositeInvalidKeyRejected=true
rawMapIsTabular=true
mapIndexByKey=true
mapRowNames=true
mapRowTypes=true
mapRowCount=true
mapContainsIndex=true
mapIndexLookup=true
mapMissingKey=true
mapNoOrderAssumed=true
tabularTypeAcceptsValue=true
nestedMapIsTabular=true
nestedValueIsComposite=true
nestedRecordFields=true
listMappedToArray=true
recordArrayMapped=true
enumMappedToString=true
proxyRecordRestored=true
proxyMapRestored=true
proxyNestedMapRestored=true
proxyListRestored=true
proxyArrayRestored=true
proxyEnumRestored=true
proxyOperationRoundTrip=true
rawOperationReturnsComposite=true
rawOperationValue=true
metadataListsCompositeAttribute=true
metadataListsTabularAttribute=true
manualCompositeBuilt=true
manualSchemaAcceptsRow=true
manualTabularBuilt=true
manualIndexCalculation=true
manualIndexLookup=true
duplicateIndexRejected=true
wrongIndexTypeRejected=true
platformMemoryIsComposite=true
platformMemoryItems=true
platformMemoryFromWorks=true
platformTypedProxyWorks=true
snapshot=rental,14
counters=12,2
manualRow=alpha,4
unregistered=true
```

**50/50 guarded assertions PASS**, cộng ba dòng hiển thị kết quả cố định. `check(name,condition)` ném `AssertionError` nếu một điều kiện sai và **chỉ khi đúng** mới in `name=true`. Test biên dịch bằng `javac --release 17` và chạy trên Windows OpenJDK 24. Không in con số heap biến động, không dùng kết quả giả lập.

### 8.5. Những kết quả quan trọng nhất

| Kiểm thử | Ý nghĩa |
| --- | --- |
| `interfaceRecognized` | `DashboardMXBean` public/naming convention được JMX nhận là MXBean |
| `rawSnapshotIsComposite` | Record trên interface xuất thành CompositeData |
| `recordItems` / `recordOpenTypes` / `recordValues` | Schema trường và dữ liệu đúng; Long/Boolean/String |
| `compositeInvalidKeyRejected` | Không được truy cập item không định nghĩa |
| `rawMapIsTabular` / `mapIndexByKey` | Map được chuyển thành bảng index theo `key` |
| `mapRowNames` / `mapRowTypes` | Mỗi table row có key:String, value:Integer |
| `mapIndexLookup` / `mapMissingKey` | Dùng Object[] index đúng, null khi không tìm thấy index |
| `nestedValueIsComposite` / `nestedRecordFields` | Giá trị lồng là CompositeData |
| `listMappedToArray` | Raw List<String> thành String[] |
| `recordArrayMapped` | Raw Snapshot[] thành CompositeData[] |
| `enumMappedToString` | Enum State.READY thành String |
| `proxyRecordRestored` / `proxyMapRestored` | Typed MXBean proxy tái dựng record/Map |
| `proxyNestedMapRestored` / `proxyListRestored` / `proxyArrayRestored` | Typed proxy tự reconstruct cấu trúc lồng/collection/array |
| `proxyOperationRoundTrip` / `rawOperationReturnsComposite` | Lời gọi operation hai chiều chuyển kiểu đúng |
| `metadataListsCompositeAttribute` / `metadataListsTabularAttribute` | JMX metadata mô tả raw types chính xác |
| `manualCompositeBuilt` / `manualTabularBuilt` | Có thể tạo OpenData bằng support classes |
| `duplicateIndexRejected` | TabularDataSupport ngăn index trùng |
| `wrongIndexTypeRejected` | TabularData.get không chấp nhận index type sai |
| `platformMemoryIsComposite` / `platformMemoryFromWorks` | Built-in MemoryMXBean trả raw CompositeData và đổi về MemoryUsage |
| `platformTypedProxyWorks` | Typed proxy tới platform MXBean hoạt động |
| `unregistered` | Cleanup ObjectName thành công |

Không cần giả định `TabularData.values()` trả thứ tự `ok` rồi `errors`. Ví dụ truy cập từng key theo tên để stdout ổn định.

### 8.6. Tại sao không dùng external JMX server?

`MBeanServerFactory.newMBeanServer()` tạo MBeanServer cục bộ và **không tự mở socket JMX remote**. Điều đó đủ để test mapping. Bật remote JMX chỉ để học OpenData thường không cần thiết, dễ kéo theo cấu hình mạng, authentication, TLS và quyền vận hành. Chỉ sử dụng remote connector nếu ứng dụng thực có yêu cầu và security policy phù hợp.

## 9. Tương thích schema khi ứng dụng thay đổi

CompositeType, TabularType và MXBean mapping giúp client khám phá dữ liệu, nhưng **không bảo đảm tự động tương thích với mọi thay đổi của model**.

### 9.1. Thêm trường vào record/CompositeType

Nếu bản mới thêm `Snapshot(String service,long requests,boolean healthy,String region)`, raw Generic Client có thể đọc `CompositeType.keySet()` để phát hiện `region`. Nhưng typed proxy cũ/new có thể yêu cầu schema và constructor tương thích; không giả định việc thêm trường luôn backward-compatible.

Java SE 26 định nghĩa quy tắc reconstruct record từ CompositeData bằng canonical constructor với fields cần thiết; nếu dữ liệu không chứa component cần, reconstruction không tự thành công. Thử nghiệm phiên bản cũ/mới là bắt buộc khi có JMX consumers khác nhau.

### 9.2. Thay tên hoặc kiểu item

- Đổi `requests:long` sang `requests:String` thay đổi `SimpleType.LONG` thành `STRING`.
- Đổi `service` thành `name` làm old clients không tìm thấy `service`.
- Thay `Map<String,Integer>` thành `List<Integer>` đổi raw result `TabularData` thành array.
- Đổi map key type thay index OpenType của table, nên `get(new Object[]{"ok"})` có thể không hợp lệ.

Hãy xem chúng như **API contract changes** của management surface, không chỉ là refactor internal.

### 9.3. Đừng tin Java serialization hoặc type names là tương thích tự động

MXBean Open Data chuẩn hóa dạng dữ liệu để client không cần server model classes, nhưng **không** tự thực hiện migration schema cho client code. Tên field, type descriptions, indexNames và nguyên tắc nullability phải được test.

Nếu interface khai báo types không convertible, đăng ký MXBean hoặc thao tác conversion có thể ném **`NotCompliantMBeanException`** hoặc các lỗi mapping phù hợp. Những lỗi này khác với `InvalidKeyException` khi truy cập item không có.

### 9.4. Nguyên tắc tương thích tốt

1. Giữ tên/schema items ổn định với clients lâu dài.
2. Thêm trường chỉ khi đã test khả năng đọc của raw và typed consumers hiện hữu.
3. Giữ indexNames của TabularType rõ ràng; nếu thay khóa, coi là thay API.
4. Chỉ dùng Java values có mapping OpenType hợp lệ.
5. Với custom classes, thiết kế reconstruct path (record canonical constructor hoặc static from/constructor annotations) rõ ràng.
6. Test remote JMX Open Data ở môi trường staging nếu deployment thật có remote clients.
7. Đừng expose graph cyclic hoặc toàn object nội bộ nhạy cảm qua management endpoints.
8. Đo kích thước/chi phí của attributes có maps/tables lớn.
9. Không suy ra schema từ method source của server ở client generic; đọc `MBeanInfo`/`OpenType`.

## 10. An toàn và vận hành JMX/MXBean

### 10.1. Local và remote JMX khác threat model

Ví dụ chạy local MBeanServer trong cùng JVM process. Trong production, JMX connector remote có thể expose thông tin JVM/threads/memory, configuration, hay cả operations thay đổi hành vi ứng dụng. **Không** bật cổng remote chỉ vì cần xem một `CompositeData`. Nếu phải dùng remote, áp authentication, authorization, TLS, network isolation và chính sách audit của nền tảng đang triển khai.

### 10.2. Expose một snapshot có kiểm soát

`CompositeData` chứa một số field, `TabularData` có thể chứa hàng nghìn entries. Tránh trả raw personal data, tokens, credentials, API keys, stacktraces nhạy cảm hoặc một map vô hạn. Hãy giới hạn số items/rows và tính toán metrics theo ngân sách CPU/memory.

### 10.3. Chi phí conversion

MXBean mapping có thể convert collections, nested records và arrays. Chi phí ấy không miễn phí. Với polling dày hoặc remote JMX, đừng trả `Map<String,Snapshot>` tăng không giới hạn. Thiết kế bounded management view và tránh iterate object graph lớn trong getters.

### 10.4. Thread safety của model

MBean server có thể gọi getters/operations đồng thời với thread ứng dụng. Một record result là immutable, nhưng **nguồn tạo record** có thể lấy số liệu từ concurrent structures. Dùng snapshots đồng nhất khi có yêu cầu, không coi automatic conversion là synchronized transaction.

### 10.5. Khi cần monitoring nhiều chiều

MXBeans hữu ích cho trạng thái quản trị và drill-down theo JMX. Với time-series metrics, high-cardinality tags hoặc ingestion lớn, cân nhắc hệ thống metrics/observability chuyên dụng có pagination, aggregation, retention và permissions. TabularData không phải một metrics database.

## 11. Troubleshooting: đọc sai cấu trúc kết quả

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ClassCastException: CompositeData → Snapshot` | Đang đọc **raw** JMX attribute | Đọc fields hoặc dùng `JMX.newMXBeanProxy` |
| `ClassCastException: TabularData → Map` | MXBean Map raw thành table | Đọc TabularData hoặc typed proxy |
| `InvalidKeyException` với CompositeData | Sai tên item/case | Inspect `CompositeType.keySet` |
| `ClassCastException: Integer → Long` | Nhầm `SimpleType.INTEGER`/`LONG` | Inspect `CompositeType.getType` |
| `TabularData.get("ok")` không compile | Signature yêu cầu `Object[]` | `get(new Object[]{"ok"})` |
| `TabularData.get(...)` ném InvalidKeyException | Sai số phần tử/type index | Inspect `TabularType.getIndexNames` |
| `get(new Object[]{"unknown"}) == null` | Không có row với index đúng type | Xử lý absence |
| `KeyAlreadyExistsException` khi `put` | Index trùng, put không overwrite | Validate unique keys hoặc thiết kế update phù hợp |
| `InvalidOpenTypeException` khi thêm row | CompositeType không khớp rowType | Sửa schema/field types |
| Nested `row.get("value")` không phải DTO | Value đã map thành CompositeData | Recursively decode schema/proxy |
| `List<String>` raw là `String[]` | Collection mapping của MXBean | Cast đúng array, không List |
| `State.READY` raw là String | Enum mapping | Dùng enum-aware typed proxy nếu cần |
| Proxy record reconstruct thất bại | Missing/changed fields/type không tương thích | Test canonical constructor và schema version |
| Không đăng ký được MXBean | Interface không compliant / unsupported mapping | Dùng public MXBean interface + convertible types |
| `getAttribute("snapshot")` sai | JMX attribute thường là `Snapshot`, không phải item `snapshot` | Dùng đúng attribute name/case |
| Metadata không có kiểu DTO class | JMX mô tả OpenData type | Đọc `MBeanInfo` descriptors |
| Tabular rows xuất ra thứ tự khác | Map/table iteration không có order guarantee | Lookup theo index hoặc sort |
| HeapMemoryUsage luôn thay đổi | Đây là runtime metric | Assert invariants, không hardcode số bytes |
| Remote JMX lỗi dù local chạy | Connector/network/auth/TLS riêng | Kiểm tra config & security policy, không bỏ xác thực |

### 11.1. Case sensitivity của attribute và item

MXBean interface method `getSnapshot()` tạo **attribute name `Snapshot`** ở JMX level. Bên trong `CompositeData` mapped từ record/getters, item names thường là `snapshotComponent` hoặc `service`, `requests`, `healthy` **viết thường** theo quy tắc. Không nhầm tên **attribute** với **item name**.

### 11.2. JMX getAttribute và invoke không giống nhau

- `server.getAttribute(name, "Snapshot")` để đọc attribute.
- `server.invoke(name, "echo", params, signature)` để gọi operation.
- Method `getSnapshot` không phải gọi `invoke(name,"getSnapshot",...)` mặc định.
- Các operation signatures trong raw MXBean cần **Open Data parameter types**; typed MXBean proxy tự chuyển kiểu.

### 11.3. Null và schema

Open Data có các trường hợp null values được phép tùy kiểu/contract và mapping. Code client phải kiểm tra null trước khi cast/unbox hoặc access nested data. Đừng giả định mọi row có nested CompositeData non-null chỉ vì schema nói field thuộc CompositeType.

## 12. Checklist kiểm tra result MXBean

- Xác định đúng `ObjectName`, tên attribute hay operation và kết nối JMX.
- Kiểm tra MXBean interface được xác định đúng (public, tên kết thúc `MXBean` hoặc `@MXBean`).
- Biết mình đang dùng **raw JMX** hay **typed proxy**, không cast nhầm kết quả.
- Nếu kết quả CompositeData: lấy `getCompositeType` và kiểm tra `keySet/getType`.
- Nếu kết quả TabularData: lấy `getTabularType`, `getRowType`, `getIndexNames`.
- Đối với Map, nhớ rows có `key` và `value`, index by `key`.
- Lookup table bằng `new Object[]{indexValue}`, không cast index key từ `keySet` thành Object[].
- Đọc các nested values theo đúng OpenType: CompositeData trong TabularData, arrays, scalars.
- Kiểm tra `SimpleType.INTEGER` và `SimpleType.LONG` đúng boxing types.
- Nếu cần Java types, dùng `JMX.newMXBeanProxy` và reconstructible declared types.
- Nếu tự tạo OpenData, validate schema và uniqueness của index.
- Tránh dựa vào ordering của Map/table hoặc biến động của metrics.
- Test cả invalid item name, invalid index type và duplicate index.
- Test schema/version compatibility cho clients hiện có.
- Không đưa thông tin nhạy cảm hoặc unbounded tables ra remote JMX.
- Nếu dùng remote connectors, áp authn/authz/TLS và network isolation.
- Đóng/cleanup registrations/connectors dùng trong integration test.

## 13. Bài tập tự luyện

**Bài 1 — Tự khám phá CompositeType:** Thêm record component `region` vào `Snapshot`. Kiểm tra `getCompositeType().keySet()` trên raw client và typed proxy. Kết luận về schema compatibility.

**Bài 2 — Đọc CompositeData bằng getAll:** Truy vấn `getAll(new String[]{"service","healthy","requests"})`; kiểm tra đúng thứ tự values. So với `get(String)` từng lần.

**Bài 3 — Sai tên field:** Gọi `snapshot.get("Requests")` thay `"requests"`. Vì sao `InvalidKeyException`? Kiểm tra schema thay vì đoán case.

**Bài 4 — Map → TabularData:** Thêm entry `"queued"→4` vào counters. Sau raw getAttribute, dùng `get(new Object[]{"queued"})` để đọc key/value.

**Bài 5 — Index kiểu sai:** Thử `table.get(new Object[]{123})` trong bảng index String. Bắt `InvalidKeyException` và so với `get(new Object[]{"missing"}) == null`.

**Bài 6 — Duplicate index:** Dùng `TabularDataSupport.put(row)` hai lần. Tại sao không overwrite như `HashMap.put`? Hãy bắt đúng `KeyAlreadyExistsException`.

**Bài 7 — Nested Map:** Với `Map<String,Snapshot>`, đọc raw row `"api"`, cast `row.get("value")` thành CompositeData và đọc `requests`.

**Bài 8 — Collections:** Quan sát `List<String> getOwners()` thành raw `String[]` và typed proxy trở lại List. Giải thích vì sao không nên test concrete List implementation.

**Bài 9 — Records:** Đổi Java record sang class có `getService`/`getRequests`/`isHealthy`. Thiết kế một reconstruct path hợp lệ khi proxy trả object.

**Bài 10 — Enum:** Raw JMX trả `"READY"`; typed proxy trả `State.READY`. Thử thêm enum constant mới và nghĩ về backward compatibility.

**Bài 11 — MBeanInfo:** In metadata `Snapshot`/`Counters`/`ByService`; xác minh raw types, descriptors và schema.

**Bài 12 — Built-in memory:** Đọc `java.lang:type=Memory`, `HeapMemoryUsage`, dùng `MemoryUsage.from(CompositeData)`. So sánh với typed `MemoryMXBean`. Không hardcode số bytes.

**Bài 13 — Snapshot consistency:** Thay `getSnapshot` bằng một snapshot của ba counters thay đổi đồng thời; thử khi concurrency lớn. Xác minh model có consistency guarantee ở đâu.

**Bài 14 — Security:** Thiết kế JMX access matrix: ai được xem metrics, ai được gọi operations, có thông tin nhạy cảm không, có remote connector không. Không mở JMX remote không xác thực.

## 14. Câu hỏi ôn tập

**1. MXBean có bắt buộc trả Java DTO class qua raw MBeanServer không?** Không; nó ánh xạ sang Open Data types.

**2. `CompositeType` là data hay schema?** Schema của CompositeData.

**3. `CompositeData.get("requests")` trả kiểu gì?** Object, với `SimpleType.LONG` sẽ là Long.

**4. `CompositeType.keySet()` cho biết gì?** Những tên item được khai báo trong schema.

**5. `CompositeData.get("missing")` làm gì?** Ném InvalidKeyException.

**6. `containsKey("missing")` trả gì?** False.

**7. `TabularType` mô tả gì?** RowType và indexNames của bảng.

**8. `TabularData` có rows kiểu gì?** CompositeData rows.

**9. `Map<String,Integer>` thành OpenData gì?** TabularData.

**10. Map row có những item names nào?** `key`, `value`.

**11. Index mặc định khi MXBean map Map thành TabularData là gì?** `["key"]`.

**12. `get(new Object[]{"ok"})` trả gì?** CompositeData row hoặc null nếu không có index đó.

**13. `TabularData.get(...)` nhận String trực tiếp không?** Không, nhận Object[].

**14. `TabularDataSupport.put` với index đã tồn tại có overwrite không?** Không; KeyAlreadyExistsException.

**15. Nested Map value là record có trở thành record raw không?** Không, value trong table có thể là CompositeData.

**16. `List<String>` raw JMX trông như thế nào?** String[].

**17. Enum raw có trở thành String không?** Có.

**18. Java record có cần `@ConstructorParameters` để typed proxy reconstruct không?** Không, record canonical constructor theo MXBean spec hiện hành.

**19. Khi nào dùng `JMX.newMXBeanProxy`?** Khi client có typed MXBean interface/model classes và muốn chuyển Open Data về Java types.

**20. `MBeanServer.invoke` raw operation signature có nhất thiết dùng class gốc không?** Không, dùng OpenData parameter types của MXBean.

**21. `MemoryUsage.from(CompositeData)` dùng làm gì?** Khôi phục MemoryUsage từ dữ liệu OpenData.

**22. `HeapMemoryUsage` là mutable số đo theo thời gian?** Giá trị metric thay đổi, không hardcode bytes.

**23. TabularData có guarantee iteration order không?** Đừng dựa vào điều đó; lookup theo index hoặc sort.

**24. MXBean OpenData tự bảo đảm snapshot atomic không?** Không, ứng dụng phải thiết kế consistency.

**25. Remote JMX có nên bật không auth chỉ để thử OpenData?** Không; dùng local MBeanServer cho fixture.

**26. Các APIs này thuộc module nào?** `java.management`.

**27. Java 17+ record mapping có phù hợp JDK 26 hiện nay?** Có, đã được đặc tả trong MXBean Javadoc.

**28. 50/50 tests PASS đã chứng minh production-safe?** Không; chỉ chứng minh conversion/schema/test cases ở runtime đã kiểm tra.

## Tài liệu chuẩn còn hiệu lực

- [Oracle Java SE 26 — MXBean annotation và MXBean specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): mapping rules, record types, Map→TabularData, collections, reconstruction.
- [Oracle Java SE 26 — JMX](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): `newMXBeanProxy`, typed proxy conversion.
- [Oracle Java SE 26 — CompositeData](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): `get`, `getAll`, `getCompositeType`, `containsKey`.
- [Oracle Java SE 26 — CompositeType](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeType.html): item names, OpenType của mỗi item và `isValue`.
- [Oracle Java SE 26 — CompositeDataSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeDataSupport.html): dựng CompositeData đúng type/schema.
- [Oracle Java SE 26 — TabularData](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularData.html): index lookup, size, row collection và put constraints.
- [Oracle Java SE 26 — TabularType](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularType.html): rowType và indexNames.
- [Oracle Java SE 26 — TabularDataSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularDataSupport.html): implementation và unique indexes.
- [Oracle Java SE 26 — OpenType](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/OpenType.html): base Open Data type.
- [Oracle Java SE 26 — MemoryUsage](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html): `MemoryUsage.from(CompositeData)`, init/used/committed/max.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MBeanServer, Memory MXBean ObjectName.
- [Oracle Java SE 26 — java.management module](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/module-summary.html): các JMX management/openmbean APIs.
- [Oracle Java SE 26 — java.lang.management package](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/package-summary.html): direct và indirect access to platform MXBeans.

**Ghi nhớ:** Một MXBean có thể khai báo Java `record`/`Map`/`List` nhưng raw `MBeanServer` trả **`CompositeData`/`TabularData`/arrays**. `CompositeType` và `TabularType` là schema; `CompositeData` và `TabularData` là values. Đối với `Map<K,V>`, hàng có `key`/`value`, index là `key`. Đọc bảng bằng `get(new Object[]{...})` và structure lồng qua `CompositeData`; không cast trực tiếp sang Java DTO/Map khi dùng raw JMX. Muốn typed Java, dùng `JMX.newMXBeanProxy`. Ví dụ Java17+ đã xác nhận **50/50 assertions PASS** với local MXBean, nested data, explicit support types và JVM MemoryMXBean thật trên OpenJDK 24.
