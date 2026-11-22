# Đổi kiểu attribute và tương thích với proxy trong Spring Framework JMX

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Hiểu **kiểu dữ liệu của JMX attribute** là một phần của management API contract, không chỉ tên attribute.
- Phân biệt Java type của getter/setter, type được công bố trong \`MBeanAttributeInfo\` và giá trị mà JMX client nhận được.
- Nhận diện breaking changes khi đổi \`int\` sang \`long\`, primitive sang wrapper, \`String\` sang enum, hoặc một Java class sang \`CompositeData\`/Open Type.
- Giải thích vai trò của **Spring AOP proxy**, JDK dynamic proxy, class-based proxy và target class khi exporter phát hiện metadata và thực thi attribute accessor.
- Hiểu vì sao đổi kiểu method trên interface hoặc implementation có thể làm JMX contract thay đổi, dù tên attribute và ObjectName vẫn giữ nguyên.
- Thiết kế **management facade**, compatibility attributes và kế hoạch migration để giữ client cũ hoạt động.
- Dùng \`MBeanServer.getMBeanInfo\`, \`getAttribute\` và integration test để xác minh type thực tế trước và sau thay đổi.
- Kiểm soát read/write semantics và tránh bỏ qua transaction/security advice khi thay đổi proxy/exporter.

## 1. JMX attribute là hợp đồng có kiểu

Trong Java Management Extensions, MBean có thể công bố một attribute:

\`\`\`text
ObjectName: learning.jmx:type=Queue,name=Primary
Attribute: QueueDepth
Type: int
Readable: true
Writable: false
\`\`\`

Một client có thể gọi:

\`\`\`java
Object value = connection.getAttribute(
    objectName,
    "QueueDepth"
);

Integer depth = (Integer) value;
\`\`\`

Nếu developer đổi getter:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return service.depth();
}
\`\`\`

thành:

\`\`\`java
@ManagedAttribute
public long getQueueDepth() {
    return service.depth();
}
\`\`\`

thì JMX attribute có thể vẫn mang tên \`QueueDepth\`, nhưng metadata type đổi từ \`int\` sang \`long\` và giá trị trả về có thể được boxed thành \`Long\` thay vì \`Integer\`.

Client ép kiểu \`Integer\` có thể gặp \`ClassCastException\`.

**Kết luận đầu tiên:** Giữ tên attribute là cần thiết, nhưng **chưa đủ** để đảm bảo tương thích JMX client. Type và semantics phải được quản lý như một phần contract.

## 2. Những thành phần tạo nên contract attribute

Một JMX attribute nên được mô tả bởi nhiều chiều:

| Thành phần | Ví dụ | Rủi ro khi thay đổi |
|---|---|---|
| MBean ObjectName | \`learning.jmx:type=Queue,name=Primary\` | Client không tìm thấy MBean |
| Attribute name | \`QueueDepth\` | AttributeNotFoundException |
| JMX type | \`int\`, \`long\`, \`java.lang.String\` | Cast/conversion failure |
| Readability | \`true\` | Client không còn đọc được |
| Writability | \`false\` | Mở thêm khả năng sửa trạng thái |
| Is-getter semantics | \`isPaused()\` | Có thể đổi metadata boolean getter |
| Value semantics | Số jobs đang chờ | Client đọc dữ liệu sai nghĩa |
| Unit | Count, millis, bytes | Alert sai ngưỡng |
| Nullability | Giá trị luôn có hay có thể null | Client không xử lý được null |
| Representation | Primitive/String/Open Type | Serialization/compatibility khác |
| Security policy | Caller nào đọc/ghi được | Rủi ro quản trị |

Không nên chỉ so sánh source code hoặc tên method để khẳng định một phiên bản JMX API tương thích với phiên bản trước.

## 3. Type công bố không giống hoàn toàn runtime boxed class

Một getter:

\`\`\`java
@ManagedAttribute
public int getActiveWorkers() {
    return 4;
}
\`\`\`

thường có metadata:

\`\`\`text
name=ActiveWorkers
type=int
\`\`\`

Nhưng Java API \`MBeanServer.getAttribute(...)\` trả về \`Object\`. Giá trị \`int\` primitive sẽ được boxed thành \`Integer\`.

Ví dụ:

\`\`\`java
Object value = server.getAttribute(name, "ActiveWorkers");

System.out.println(value.getClass().getName());
// java.lang.Integer
\`\`\`

Tương tự:

- \`long\` trong metadata thường tương ứng \`Long\` ở giá trị trả về.
- \`boolean\` thường tương ứng \`Boolean\`.
- \`double\` thường tương ứng \`Double\`.

**Đừng kiểm tra metadata bằng cách so sánh với runtime class name của giá trị boxed.** Dùng \`MBeanAttributeInfo.getType()\` cho type contract, và kiểm tra runtime value riêng.

## 4. Ví dụ thay đổi int sang long

Phiên bản 1:

\`\`\`java
@ManagedAttribute(description = "Processed requests since startup")
public int getProcessedRequests() {
    return processedRequests.intValue();
}
\`\`\`

Phiên bản 2:

\`\`\`java
@ManagedAttribute(description = "Processed requests since startup")
public long getProcessedRequests() {
    return processedRequests.longValue();
}
\`\`\`

Lý do nâng cấp là hợp lý: \`int\` có thể tràn nếu counter lớn. Nhưng client cũ có thể đang viết:

\`\`\`java
Integer count = (Integer) connection.getAttribute(
    name, "ProcessedRequests"
);
\`\`\`

Sau đổi type, cast thất bại.

Nếu client dùng:

\`\`\`java
Number count = (Number) connection.getAttribute(
    name, "ProcessedRequests"
);

long value = count.longValue();
\`\`\`

nó có thể thích nghi với một số kiểu số khác nhau, nhưng **không được dựa vào client tolerant để bỏ qua migration contract**. Những scripts, exporters và monitoring rules khác có thể vẫn kỳ vọng type cũ.

Một thay đổi kiểu dù giúp sửa overflow vẫn phải được coi là schema evolution và được thông báo/kiểm thử.

## 5. Giữ attribute cũ, thêm attribute mới

Một cách migration thường rõ ràng là giữ attribute cũ và thêm attribute có tên thể hiện type/range mới.

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=RequestMetrics,name=Primary"
)
public class RequestMetricsManagement {

    private final AtomicLong processed = new AtomicLong();

    @ManagedAttribute(
        description = "Legacy 32-bit processed request count"
    )
    public int getProcessedRequests() {
        long value = processed.get();

        // Chính sách chuyển đổi phải được xác định rõ.
        return value > Integer.MAX_VALUE
                ? Integer.MAX_VALUE
                : (int) value;
    }

    @ManagedAttribute(
        description = "64-bit processed requests since startup"
    )
    public long getProcessedRequestsLong() {
        return processed.get();
    }
}
\`\`\`

Trong giai đoạn migration:

- Client cũ tiếp tục đọc \`ProcessedRequests\` với type \`int\`.
- Client mới dùng \`ProcessedRequestsLong\` có type \`long\`.
- Documentation nói rõ việc legacy attribute dùng saturating value khi vượt \`Integer.MAX_VALUE\`, hoặc một policy khác đã được thiết kế.
- Monitoring alerts không âm thầm hiểu số được clamp thành tổng chính xác.
- Khi loại bỏ legacy attribute, đây là breaking change được quản lý.

**Lưu ý:** Clamp \`Integer.MAX_VALUE\` chỉ là một ví dụ, không phải default behavior của Spring/JMX. Nếu semantics là số tích lũy chính xác, clamp có thể gây hiểu nhầm; cần ghi rõ hoặc chọn một chiến lược khác phù hợp.

## 6. Đổi primitive thành wrapper

Ví dụ từ:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return depth;
}
\`\`\`

sang:

\`\`\`java
@ManagedAttribute
public Integer getQueueDepth() {
    return depth;
}
\`\`\`

Tên attribute có thể không đổi nhưng metadata có thể đổi từ \`int\` sang \`java.lang.Integer\`.

Điều đó tạo khác biệt về type contract và có thể mở thêm khả năng trả \`null\`.

Không nên nghĩ “boxing/unboxing tự động nên JMX client không bị ảnh hưởng”. JMX metadata mô tả kiểu khai báo, và một số client dựa vào type string để chuyển đổi hoặc kiểm tra hợp lệ.

Khi refactor này không mang lại ý nghĩa quản trị mới, thường nên **giữ return type cũ tại management facade**:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    Integer value = service.queueDepthOrNull();
    return value == null ? 0 : value;
}
\`\`\`

Nhưng giá trị 0 khi null phải được định nghĩa hợp lý. Nếu null nghĩa là “không có dữ liệu” chứ không phải “queue rỗng”, trả 0 là sai semantics. Khi đó nên tạo attribute trạng thái riêng như \`QueueDepthAvailable\` hoặc contract mới có cách biểu diễn missing rõ ràng.

## 7. Đổi String sang enum

Một getter quản trị có thể ban đầu trả:

\`\`\`java
@ManagedAttribute
public String getState() {
    return "RUNNING";
}
\`\`\`

Sau refactor nghiệp vụ:

\`\`\`java
public enum WorkerState {
    STARTING, RUNNING, PAUSED, FAILED
}
\`\`\`

Nếu đổi getter JMX thành:

\`\`\`java
@ManagedAttribute
public WorkerState getState() {
    return service.state();
}
\`\`\`

type contract thay đổi, và một remote JMX client có thể cần class enum phù hợp trong classpath hoặc gặp các giới hạn của MBean adaptation.

Cách giữ contract ổn định:

\`\`\`java
@ManagedAttribute
public String getState() {
    return service.state().name();
}
\`\`\`

Chú ý semantics giá trị chuỗi vẫn quan trọng. Nếu enum thêm state mới, client dùng switch trên danh sách cố định cũng cần xem lại. Tương thích type không tự đồng nghĩa tương thích **tập giá trị**.

## 8. Đổi sang custom object và Open Types

Một MBean attribute trước đây trả \`String\`:

\`\`\`java
@ManagedAttribute
public String getSummary() {
    return "pending=5,active=2";
}
\`\`\`

Sau đó muốn trả object:

\`\`\`java
public record QueueSummary(long pending, long active) {
}
\`\`\`

Việc công bố trực tiếp custom Java object qua Standard MBean/JMX remote có thể yêu cầu class serializable và client có classpath tương ứng; không nên giả định mọi client sẽ giải mã thành công.

Với hệ thống JMX dùng rộng rãi, có thể cân nhắc:

- Các primitive/String attributes riêng.
- \`CompositeData\`, \`TabularData\` hoặc Open Types nếu phù hợp.
- MXBean contract, khi muốn Java types được ánh xạ sang Open Types theo quy tắc MXBean.
- Một API khác với schema/versioning rõ nếu dữ liệu có cấu trúc phức tạp.

**Quan trọng:** Đổi từ Standard MBean sang MXBean hoặc Open Type representation có thể làm thay đổi metadata type và runtime values. Cần kiểm chứng \`MBeanInfo\` cùng dữ liệu \`getAttribute\` thực tế, không chỉ kiểm tra Java return type.

## 9. Setter và sự tương thích read/write

Giả sử attribute writable:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int value) {
    validate(value);
    maxWorkers = value;
}
\`\`\`

Khi getter đổi thành \`long\` nhưng setter vẫn nhận \`int\`, các quy tắc JavaBeans/JMX về getter-setter compatibility có thể khiến metadata không còn như dự kiến hoặc exporter báo lỗi tùy assembler.

Không nên để getter và setter khác type mà không có thiết kế rõ.

Nếu contract cần đổi từ \`int\` sang \`long\`:

1. Xác định tác động với client đọc.
2. Xác định tác động với client ghi qua \`setAttribute\`.
3. Bảo đảm getter/setter có type tương thích theo metadata.
4. Kiểm tra \`MBeanAttributeInfo.getType()\`, \`isReadable()\`, \`isWritable()\`.
5. Kiểm tra việc ghi giá trị ở ranh giới JMX.
6. Nếu breaking change lớn, công bố một attribute mới thay vì đổi tại chỗ.

## 10. Spring AOP proxy liên quan thế nào đến kiểu attribute?

Spring AOP có thể trả một proxy thay vì target bean:

\`\`\`text
Spring ApplicationContext
       |
       v
AOP proxy (JDK dynamic proxy / class-based proxy)
       |
       v
Target service
\`\`\`

Đây là yếu tố quan trọng khi JMX exporter xác định bean type, đọc annotation metadata và gọi accessor.

Ví dụ target class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
public class WorkerPoolServiceImpl implements WorkerPoolService {

    @ManagedAttribute
    public long getCompletedTasks() {
        return completed.get();
    }

    // ...
}
\`\`\`

Nếu một JDK dynamic proxy chỉ triển khai \`WorkerPoolService\` và interface không chứa \`getCompletedTasks()\`, exporter cần nhận diện target metadata và đường gọi phù hợp. Nếu không, attribute có thể không xuất hiện hoặc không invocable qua proxy theo cấu hình cụ thể.

Class-based proxy thường giữ nhiều public methods của concrete class hơn, nhưng không phải bảo đảm tuyệt đối; final class/method và các vấn đề khác vẫn có thể ảnh hưởng.

**Không đồng nhất “đổi kiểu attribute” với “đổi loại proxy”**. Đây là hai biến độc lập và cần test riêng.

## 11. JDK dynamic proxy và interface contract

Ví dụ interface:

\`\`\`java
public interface WorkerPoolService {
    int getActiveWorkers();
}
\`\`\`

Implementation:

\`\`\`java
public class WorkerPoolServiceImpl implements WorkerPoolService {

    @Override
    public int getActiveWorkers() {
        return 4;
    }
}
\`\`\`

Nếu muốn thay type interface method sang \`long\`, Java interface contract cũng phải đổi. Một thay đổi như:

\`\`\`java
public interface WorkerPoolService {
    long getActiveWorkers();
}
\`\`\`

có thể yêu cầu cập nhật implementation và mọi client Java đang compile against interface. Với JMX, type metadata có thể đổi nếu operation/attribute được công bố từ method mới.

Trong một JDK proxy, bề mặt methods mà proxy triển khai thường lấy từ interfaces. Vì vậy thay đổi interface method là một thay đổi đáng chú ý, cả ở Java API lẫn JMX API khi chúng dùng chung.

**Giải pháp:** Tách **management facade** khỏi service interface để Java refactor không tự kéo theo JMX type changes.

## 12. Management facade bảo toàn kiểu JMX

Service nghiệp vụ mới có type \`long\`:

\`\`\`java
public interface WorkerPoolService {
    long activeWorkerCount();
}
\`\`\`

Facade giữ contract cũ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
public class WorkerPoolManagement {

    private final WorkerPoolService service;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getActiveWorkers() {
        long value = service.activeWorkerCount();

        if (value > Integer.MAX_VALUE) {
            throw new IllegalStateException(
                "Active worker count exceeds legacy int range"
            );
        }
        return Math.toIntExact(value);
    }

    @ManagedAttribute
    public long getActiveWorkersLong() {
        return service.activeWorkerCount();
    }
}
\`\`\`

Ở đây:

- Service API có thể dùng \`long\` đúng yêu cầu nghiệp vụ.
- JMX legacy \`ActiveWorkers\` vẫn là \`int\`.
- Attribute mới \`ActiveWorkersLong\` có contract \`long\`.
- Nếu giá trị vượt phạm vi legacy, policy đã được công bố: báo lỗi thay vì âm thầm overflow.

Đây chỉ là một policy minh họa; trong production, có thể cân nhắc clamp, unavailable flag, metrics khác hoặc cắt chuyển qua version mới. Quan trọng là **không âm thầm làm sai số liệu**.

Facade có thể gọi Spring service proxy để giữ transaction/security/logging advice cần thiết, thay vì đăng ký target thô ngoài Spring lifecycle.

## 13. Không lấy runtime proxy class làm contract

Ví dụ anti-pattern:

\`\`\`java
String objectName =
    "learning.jmx:type=" + bean.getClass().getSimpleName();
\`\`\`

Nếu \`bean\` là JDK proxy hoặc class-based proxy, runtime class name có thể thay đổi theo Spring/JDK version hoặc cấu hình AOP.

Hãy giữ ObjectName tường minh:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
\`\`\`

Đồng thời giữ getter names và return types trên management facade ổn định. Một ObjectName không đổi nhưng metadata type đã đổi vẫn có thể làm client cũ thất bại.

## 14. Đừng bỏ proxy để “sửa type” mà mất advice

Một giải pháp vội là lấy target object đằng sau Spring AOP proxy rồi export trực tiếp.

Rủi ro:

- JMX invocation không đi qua security advice hoặc transaction interceptor.
- Target không phải Standard MBean hợp lệ nếu không có wrapper/assembler.
- MBean lifecycle không còn do Spring exporter quản lý chặt chẽ.
- Metadata có thể khác proxy interface đang được ứng dụng sử dụng.
- Một thay đổi target lifecycle/scope có thể tạo registration cũ.

Thay vào đó, management facade nên gọi **Spring-managed service proxy**. Nếu cần export proxy có chủ đích, hãy xác định một management interface rõ ràng, kiểm tra method visibility và test invocation qua JMX.

Không có quy tắc tuyệt đối rằng “luôn export target” hay “luôn export proxy”; mục tiêu là công bố một management contract ổn định và giữ đúng call path.

## 15. Dùng AopUtils để quan sát proxy

Trong Spring AOP:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerPoolService");

System.out.println(
    "Runtime class: " + bean.getClass().getName()
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean)
);
System.out.println(
    "Is proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "Class proxy: " + AopUtils.isCglibProxy(bean)
);
\`\`\`

Kết quả giúp chẩn đoán:

- Bean có thật sự là proxy không?
- Proxy dùng interfaces hay target class?
- Target class nào chứa metadata JMX?
- Những methods có ở interface proxy không?

Nhưng \`AopUtils\` không thay thế việc kiểm tra contract JMX sau export. Hãy dùng \`MBeanInfo\` để biết client thực sự thấy gì.

## 16. MBeanInfo: nguồn kiểm chứng kiểu thực tế

MBeanServer cung cấp:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

Với mỗi attribute:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

Có thể thu được:

\`\`\`text
ActiveWorkers type=int read=true write=false
ActiveWorkersLong type=long read=true write=false
\`\`\`

Nếu exporter/assembler hoặc proxy strategy thay đổi, hãy so sánh metadata trước/sau ở cùng logical ObjectName.

Một test contract có thể kiểm tra cụ thể:

\`\`\`java
boolean unchanged = java.util.Arrays.stream(
    server.getMBeanInfo(name).getAttributes()
).anyMatch(a ->
    "ActiveWorkers".equals(a.getName())
    && "int".equals(a.getType())
    && a.isReadable()
    && !a.isWritable()
);

if (!unchanged) {
    throw new AssertionError(
        "JMX ActiveWorkers contract changed"
    );
}
\`\`\`

Đây là kiểm thử có thể phát hiện breaking change mà Java compiler không tự phát hiện đối với clients dùng JMX bằng chuỗi.

## 17. Kiểm thử cả metadata và giá trị trả về

Chỉ kiểm tra MBeanInfo chưa đủ nếu actual value hoặc semantics bị thay đổi.

Ví dụ:

\`\`\`java
Object value = server.getAttribute(name, "ActiveWorkers");

assertInstanceOf(Integer.class, value);
assertEquals(4, value);
\`\`\`

Sau khi thêm attribute long:

\`\`\`java
Object wider = server.getAttribute(
    name,
    "ActiveWorkersLong"
);

assertInstanceOf(Long.class, wider);
assertEquals(4L, wider);
\`\`\`

Khi test proxy, cũng cần xác nhận method invocation đi qua call path mong đợi, nhất là nếu một getter có authorization/transaction advice hoặc service dùng proxy scopes.

Nếu các attributes trả state từ cùng service, kiểm tra semantics cùng thời điểm thay vì chỉ đối chiếu kiểu.

## 18. Test thực tế với Spring context và proxy

Một integration test có thể được tổ chức như sau:

1. Tạo ApplicationContext có target service và AOP configuration.
2. Enable Spring JMX exporter cho management facade.
3. Lấy đúng MBeanServer đã cấu hình.
4. Assert ObjectName registered.
5. Dùng MBeanInfo xác nhận attribute name/type/read/write.
6. Gọi getAttribute qua MBeanServer.
7. Kiểm tra runtime value class và semantics.
8. Nếu thử JDK proxy/class proxy, chạy test theo hai configurations.
9. Đóng context, xác nhận MBean do exporter sở hữu được unregistered.

Ví dụ khung JUnit:

\`\`\`java
@Test
void jmxTypeContractRemainsStable() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(
            "testMBeanServer", MBeanServer.class
        );

        ObjectName name = new ObjectName(
            "learning.jmx:type=WorkerPool,name=Primary"
        );

        assertTrue(server.isRegistered(name));

        MBeanAttributeInfo attribute = Arrays.stream(
            server.getMBeanInfo(name).getAttributes()
        ).filter(a -> "ActiveWorkers".equals(a.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("int", attribute.getType());
        assertTrue(attribute.isReadable());
        assertFalse(attribute.isWritable());

        Object result = server.getAttribute(name, "ActiveWorkers");
        assertInstanceOf(Integer.class, result);
    }
}
\`\`\`

\`JmxTestConfiguration\` cần được định nghĩa trong dự án test để tạo server, managed resource, proxy và exporter tương ứng. Dùng server riêng giúp tránh collisions với platform MBeanServer trong tests chạy song song.

## 19. So sánh JDK proxy và class-based proxy

Một thay đổi AOP có thể làm bean runtime chuyển từ JDK proxy sang class-based proxy.

| Đặc điểm | JDK proxy | Class-based proxy |
|---|---|---|
| Bề mặt method | Methods trên interfaces proxy | Phần lớn methods của class target có thể proxy |
| Khả năng cast | Thường cast theo interface | Có thể cast theo target superclass |
| Metadata JMX trên target | Cần exporter/assembler xử lý target metadata và invocable method | Có thể nhìn methods concrete thuận tiện hơn |
| Ràng buộc | Method không có trong interface có thể không invocable qua proxy | Final class/method có thể giới hạn interception |
| Tác động type contract | Tùy interfaces và exporter | Tùy target methods và exporter |

\`proxyTargetClass=true\` có thể hữu ích trong một số trường hợp, nhưng **không phải biện pháp đổi type JMX tương thích**. Chọn proxy strategy là lựa chọn AOP; chọn JMX attribute type là thiết kế management API. Hai quyết định cần được kiểm chứng độc lập.

## 20. Kiểm tra ảnh hưởng của method-level security

Giả sử service getter:

\`\`\`java
@PreAuthorize("hasAuthority('VIEW_WORKER_POOL')")
public long activeWorkerCount() {
    return count.get();
}
\`\`\`

Nếu management facade gọi Spring-managed service proxy, method-level security advice có thể chạy theo cấu hình.

Nhưng nếu trực tiếp export target rồi gọi getter, advice có thể bị bypass. Ngoài ra, JMX connector authentication/authorization là một lớp riêng; HTTP security filter không tự bảo vệ JMX.

Khi đổi kiểu attribute và thay proxy/exporter cùng lúc, cần test:

- Client có quyền đọc thành công.
- Client không có quyền bị từ chối.
- Type metadata và value vẫn đúng.
- Operation/writable attribute không vô tình mở rộng quyền.
- Security advice thực sự chạy ở call path JMX.

Không chỉ dựa vào annotation \`@PreAuthorize\` trong source mà khẳng định JMX đã được bảo vệ.

## 21. Đổi type với remote JMX có thêm rủi ro

Remote JMX có thể truyền giá trị qua connector và serialization. Đối với primitive, wrapper và String đơn giản, thường ít phức tạp hơn custom object.

Khi đổi type sang một class mới:

- Remote client có classpath chứa class đó không?
- Giá trị có serializable theo cơ chế connector không?
- Có thay đổi \`serialVersionUID\` hoặc fields không?
- Có dùng MXBean mapping/Open Types không?
- Data size tăng bao nhiêu?
- Client xử lý null hoặc trường mới thế nào?
- Có policy bảo mật cho dữ liệu mới được công bố không?

Ngay cả khi in-process JMX client hoạt động, remote client vẫn có thể gặp lỗi decoding hoặc compatibility.

Đối với interface quản trị dùng nhiều loại client, ưu tiên type có contract rõ và ít phụ thuộc implementation Java cụ thể.

## 22. Kế hoạch migration kiểu attribute

Nếu cần thay một attribute \`int\` bằng \`long\`, có thể tiến hành theo các bước:

1. **Inventorize consumers:** scripts, dashboards, JMX exporters, operational tools và client apps.
2. **Đóng băng contract hiện tại:** ObjectName, attribute name, type, readability, writability, unit.
3. **Thêm contract mới:** attribute \`...Long\` hoặc tên thể hiện semantics mới.
4. **Giữ legacy attribute:** tiếp tục trả type cũ theo policy chuyển đổi đã định nghĩa.
5. **Cập nhật client:** dùng type mới hoặc xử lý \`Number\` khi phù hợp.
6. **Theo dõi adoption:** xác nhận consumers đã chuyển, tránh xóa sớm.
7. **Viết compatibility tests:** assert cả old và new trong migration window.
8. **Thử proxy strategies:** nếu AOP đang thay đổi, kiểm tra call path.
9. **Lập kế hoạch removal:** deprecate theo release/chính sách hỗ trợ.
10. **Triển khai có rollback:** nếu client cũ lỗi, có lộ trình khôi phục contract.

Một phép đổi kiểu cần được coi là schema evolution, không đơn giản là refactor Java.

## 23. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client ép \`Integer\` lỗi sau deploy | Getter đổi \`int\` sang \`long\` | Giữ legacy int attribute hoặc cập nhật consumer |
| Attribute name không đổi nhưng tool báo type mismatch | \`MBeanAttributeInfo.getType()\` đã đổi | Contract test, migration |
| Attribute mất sau khi bật AOP | Exporter không xử lý proxy/target metadata như kỳ vọng | Kiểm tra AopUtils, assembler và registration |
| JDK proxy không lộ getter | Method không có trên proxy interface | Dùng facade, management interface hoặc config phù hợp |
| CGLIB vẫn lỗi | Final method/class hoặc vấn đề exporter khác | Chẩn đoán MBeanInfo và call path |
| SetAttribute bị từ chối | Setter type hoặc writability thay đổi | Kiểm tra getter/setter và MBeanAttributeInfo |
| Remote client không deserialize được | Đổi sang custom object type | Open Types/MXBean hoặc contract đơn giản |
| Enum value lạ làm client lỗi | Tập giá trị được mở rộng | Client tolerant + documented states |
| Type ổn định nhưng giá trị sai | Đổi unit/semantics âm thầm | Giữ conversion hoặc tạo attribute mới |
| Security advice không chạy | Export target thô, bypass proxy | Facade gọi service proxy, test JMX path |
| Context đóng làm MBean khác biến mất | Exporter ownership/ObjectName collision | Tách naming và kiểm thử lifecycle |

## 24. Bài tập thực hành

### Bài tập 1 — Phát hiện breaking change

Ban đầu getter:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() { return 100; }
\`\`\`

Sau đổi:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() { return 100L; }
\`\`\`

Hãy viết MBeanInfo test xác nhận type \`int\`. Sau khi đổi getter, giải thích vì sao test phải fail và client cast Integer có thể bị ảnh hưởng.

### Bài tập 2 — Compatibility facade

Service mới chỉ cung cấp \`long activeWorkerCount()\`. Thiết kế facade công bố \`ActiveWorkers\` type \`int\` cho client cũ và \`ActiveWorkersLong\` type \`long\` cho client mới. Định nghĩa chính sách nếu giá trị vượt range int.

### Bài tập 3 — Primitive vs wrapper

Thử đổi getter từ \`int\` sang \`Integer\`. Kiểm tra \`MBeanInfo.getAttributes()\` và runtime \`getAttribute\`. Giải thích khác biệt giữa metadata type và boxed value class.

### Bài tập 4 — Proxy strategy

Tạo target service có interface và AOP advisor thật. Chạy test với JDK dynamic proxy và class-based proxy. Kiểm tra ObjectName, attribute name, type và khả năng đọc qua JMX.

### Bài tập 5 — Remote type compatibility

Một custom MBean attribute trả object class \`QueueSummary\`. Client chạy JVM khác thiếu class này. Hãy đề xuất contract dùng primitive attributes hoặc CompositeData/MXBean để hạn chế coupling.

## 25. Checklist khi đổi kiểu attribute

1. ObjectName có đổi không?
2. Attribute name có đổi không?
3. Metadata type trước/sau là gì?
4. Giá trị runtime có boxed type nào?
5. Readable/writable semantics có đổi không?
6. Getter/setter có type tương thích không?
7. Unit và nullability có đổi không?
8. Có client cast trực tiếp primitive wrapper không?
9. Có remote serialization/classpath dependency mới không?
10. Proxy interface/target method có thay đổi không?
11. Exporter có còn nhận metadata đúng không?
12. Invocation có đi qua advice cần thiết không?
13. Có contract test qua MBeanInfo và getAttribute không?
14. Có kế hoạch deprecation/migration không?
15. Có rollback plan nếu consumer lỗi không?

## 26. Ghi nhớ cốt lõi

- **Type của JMX attribute là một phần contract**, giống tên và ObjectName.
- \`int\` và \`long\`, primitive và wrapper, String và enum/custom object có thể tạo khác biệt runtime/metadata quan trọng.
- Không dựa vào autoboxing để khẳng định compatibility của JMX clients.
- Spring AOP proxy có thể ảnh hưởng metadata discovery và method invocation; cần kiểm chứng MBeanInfo trên bean thực tế đã export.
- Management facade giúp giữ JMX type và naming ổn định trong khi service API thay đổi.
- Không bypass proxy chỉ để sửa JMX metadata nếu transaction/security advice là cần thiết.
- Khi phải đổi type, thêm attribute mới và migration có kiểm soát thường an toàn hơn đổi tại chỗ.
- Test cả metadata, returned value, writable semantics, remote representation và lifecycle.

## Tài liệu tham khảo

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
