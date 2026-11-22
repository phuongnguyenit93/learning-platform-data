# Rà soát ảnh hưởng của AOP, transaction và proxy đối với Spring Framework JMX

## 1. Mục tiêu

Trong Spring Framework, một bean được quản lý có thể đồng thời tham gia nhiều cơ chế:

- **JMX export:** MBeanExporter hoặc AnnotationMBeanExporter công bố bean thành MBean.
- **Spring AOP:** một proxy bọc bean để áp dụng logging, validation, caching, security hoặc advice khác.
- **Transaction management:** TransactionInterceptor thường triển khai hành vi @Transactional qua AOP proxy.
- **JMX access proxy:** MBeanProxyFactoryBean tạo typed client proxy để gọi MBeanServer.

Các cơ chế này phục vụ mục đích khác nhau nhưng có thể tương tác theo cách khó thấy. Nếu exporter nhận một proxy thay vì đối tượng gốc, JMX metadata và method có thể bị giới hạn bởi proxy. Nếu operation JMX được gọi không đi qua Spring AOP proxy như thiết kế, @Transactional có thể không được kích hoạt. Nếu một management operation chạy quá lâu trong transaction, hệ thống có thể giữ lock và connection trong khi client JMX chờ.

Bài học tập trung vào việc **đánh giá thiết kế**: truy vết đường gọi, xác nhận method thực sự được expose, kiểm tra transaction boundary, xác định danh tính resource và thiết lập bài kiểm thử để không suy luận sai từ annotation.

## 2. Các loại proxy cần phân biệt

| Thành phần | Đối tượng đại diện | Mục tiêu chính |
| --- | --- | --- |
| Spring AOP JDK dynamic proxy | Các interface của target | Áp dụng advice khi gọi qua proxy |
| Spring AOP class-based proxy | Lớp con của target khi proxy được tạo theo lớp | Intercept những method có thể override |
| MBeanProxyFactoryBean | MBean theo ObjectName và interface client | Chuyển method Java thành JMX attribute/operation |
| MBeanServer | Registry MBean | Dispatch lời gọi JMX tới MBean đã đăng ký |
| ModelMBean | Adapter expose POJO qua metadata | Điều phối attributes/operations của bean |

Không nên đồng nhất "Spring proxy" với "JMX proxy". Một ứng dụng có thể có cả hai:

~~~text
Java caller
   |
   v
MBeanProxyFactoryBean product
   |
   v
MBeanServerConnection
   |
   v
MBeanServer / ModelMBean
   |
   v
Spring-managed target or AOP proxy
   |
   v
TransactionInterceptor / Security advice
   |
   v
Business service
~~~

Đây là một khả năng kiến trúc, không phải cam kết mọi cấu hình đều tạo đúng đường gọi này. Phải kiểm tra object thực sự được exporter giữ và method invocation thực tế.

## 3. AOP proxy thay đổi điều gì?

Spring AOP phổ biến là **proxy-based AOP**. Advice chỉ áp dụng khi invocation đi qua proxy đã được Spring tạo.

Giả sử:

~~~java
@Service
public class PaymentService {
    @Transactional
    public void reconcile() {
        // Update database.
    }
}
~~~

Khi một bean khác inject PaymentService và gọi reconcile() qua proxy, transaction advice thường được áp dụng nếu transaction management được cấu hình phù hợp.

Nhưng một method trong cùng class tự gọi method khác qua this có thể không đi qua proxy:

~~~java
@Service
public class PaymentService {
    public void maintenance() {
        reconcile(); // Self-invocation.
    }

    @Transactional
    public void reconcile() {
        // Transaction may not be applied here via proxy AOP.
    }
}
~~~

Với cấu hình Spring AOP proxy tiêu chuẩn, lời gọi này bypass proxy. Một MBean operation gọi maintenance() không được tự động coi là có transaction chỉ vì reconcile() có annotation.

Giải pháp phù hợp thường là tách transaction method sang một Spring bean khác và gọi qua dependency đã inject, hoặc thiết kế transaction boundary tường minh ở service layer.

## 4. Đường gọi JMX và nơi có thể mất advice

Một operation JMX như:

~~~text
com.example.orders:type=Admin,name=payments
operation: reconcile()
~~~

có thể được export theo những cách khác nhau:

1. Export trực tiếp Spring bean thực tế.
2. Export một Spring AOP proxy bọc bean.
3. Export một management adapter gọi sang business service proxy.
4. Export Standard MBean riêng, không đi qua Spring business proxy.

Ở trường hợp 2, lời gọi JMX **có thể** đi qua advice nếu exporter giữ và invoke proxy đúng cách, nhưng điều này phụ thuộc interface, method visibility, metadata assembler và cấu hình exporter.

Ở trường hợp 4, nếu Standard MBean tự tạo PaymentService bằng new hoặc giữ target không phải Spring proxy, transaction advice trên bean của Spring có thể bị bỏ qua.

**Không suy ra từ @Transactional rằng JMX operation luôn chạy trong transaction.** Hãy dùng integration test quan sát TransactionSynchronizationManager.isActualTransactionActive() hoặc bằng chứng transaction thực sự trong service được gọi.

## 5. Đề xuất thiết kế: management adapter mỏng

Thay vì để exporter expose trực tiếp service nghiệp vụ, có thể dùng một adapter quản trị:

~~~text
JMX MBean
   |
   v
PaymentManagementAdapter
   |
   v
PaymentMaintenanceService (Spring bean)
   |
   +-- @Transactional boundary
   +-- validation
   +-- authorization
   +-- business invariants
   |
   v
Repository / external system
~~~

Ví dụ:

~~~java
package com.example.orders.management;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Admin,name=payments"
)
public class PaymentManagementAdapter {

    private final PaymentMaintenanceService service;

    public PaymentManagementAdapter(PaymentMaintenanceService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Reconcile pending payments")
    public void reconcile() {
        service.reconcilePending();
    }
}
~~~

Service:

~~~java
package com.example.orders.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentMaintenanceService {

    @Transactional
    public void reconcilePending() {
        // Read and update durable business state.
    }
}
~~~

Nếu PaymentMaintenanceService được inject dưới dạng Spring transactional proxy, lời gọi từ adapter sang service đi qua proxy và transaction advice có thể áp dụng. Cấu hình transaction manager và datasource vẫn phải đúng.

Lợi ích: hợp đồng JMX nhỏ, business logic không bị phụ thuộc trực tiếp vào API quản trị, và ranh giới transaction có thể kiểm thử.

## 6. JDK dynamic proxy so với class-based proxy

Spring AOP có thể dùng JDK dynamic proxy khi target có interface hoặc class-based proxy theo cấu hình.

### JDK dynamic proxy

~~~java
public interface PaymentMaintenance {
    void reconcilePending();
}
~~~

Nếu bean được proxy theo interface, những method không có trên interface proxy có thể không sẵn có khi exporter cố introspect proxy bằng type thực tế.

Ví dụ:

~~~java
public class PaymentService implements PaymentMaintenance {
    public void reconcilePending() {}

    public String internalDiagnostics() {
        return "ok";
    }
}
~~~

Proxy chỉ expose PaymentMaintenance thì internalDiagnostics() có thể không gọi được qua proxy theo cách exporter kỳ vọng, dù method tồn tại trên target class.

### Class-based proxy

Class-based proxy cho phép tương tác qua class nhưng còn những giới hạn:

- Final class không thể được subclass để tạo proxy kiểu này.
- Final method không thể được override để áp advice.
- Private method không phải join point được override theo cách proxy-based AOP này.
- Method không thể được gọi phù hợp qua proxy sẽ không nhận advice.
- Một số constructor/lifecycle behavior có thể khác so với đối tượng thuần.

**Điểm đánh giá:** phương thức công bố qua JMX có tồn tại và callable trên object thực sự được exporter sử dụng hay không?

## 7. Đừng dùng tên class proxy làm ObjectName

Một naming strategy không nên lấy tên runtime class:

~~~java
managedBean.getClass().getName()
~~~

khi bean có thể là AOP proxy. Tên có thể chứa dạng như:

~~~text
PaymentManagementAdapter$$SpringCGLIB$$0
com.sun.proxy.$Proxy...
~~~

Tên proxy phụ thuộc cấu hình/vòng đời, không phải logical identity ổn định của resource.

Nên dùng ObjectName do hợp đồng quản trị định nghĩa:

~~~text
com.example.orders:type=Admin,name=payments
com.example.orders:type=Queue,name=shipping
~~~

Từ đó JMX client không phụ thuộc implementation class hoặc kiểu proxy mà Spring tạo.

## 8. Annotation metadata và proxy

Spring JMX có các annotation:

- @ManagedResource
- @ManagedAttribute
- @ManagedOperation
- @ManagedNotification

Nếu một bean bị AOP proxy, cần kiểm tra exporter/assembler có khám phá annotation đúng target class và áp dụng method metadata chính xác không.

Ví dụ target có:

~~~java
@ManagedResource(
    objectName = "com.example.orders:type=Admin,name=payments"
)
public class PaymentManagementAdapter {

    @ManagedOperation
    public void reconcile() {}
}
~~~

Nếu exporter nhìn thấy interface proxy không mang annotation hoặc không thể resolve method target, MBeanInfo có thể không chứa operation như mong đợi. Cách xử lý không phải luôn tắt AOP; trước hết cần xác nhận Spring version, exporter configuration, bean selection và metadata assembler.

### Kiểm tra MBeanInfo

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Admin,name=payments"
);

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
~~~

Cần thấy reconcile trong danh sách operation với signature mong đợi. Nếu không, kiểm tra bean exporter đang nhận là proxy hay target và source metadata từ đâu.

## 9. Transaction không nên bao trùm thời gian tương tác với người vận hành

Một operation JMX có thể được gọi qua JConsole, script hoặc remote connector. Nếu nó được gắn @Transactional và thực thi lâu:

~~~java
@ManagedOperation
@Transactional
public void rebuildIndex() {
    // Runs for several minutes.
}
~~~

nó có thể giữ database connection, lock hoặc transaction resources trong suốt khoảng thời gian dài; timeout và rollback cũng có thể phức tạp.

Thay vì một transaction bao trùm toàn tác vụ, cân nhắc:

1. Operation JMX nhận yêu cầu và trả operation ID.
2. Service validate quyền và điều kiện.
3. Task được đưa vào worker/scheduler có kiểm soát.
4. Worker thực hiện các bước ngắn với transaction boundary riêng.
5. MBean expose trạng thái operation ID qua read-only attribute hoặc operation query.

~~~text
JMX startRebuild()
     |
     v
Validation / authorization
     |
     v
Task scheduler / job registry
     |
     v
Short transactions per batch
     |
     v
Operation status and metrics
~~~

Nếu vẫn muốn synchronous operation, cần đặt timeout, giới hạn concurrency và đảm bảo transaction duration phù hợp với yêu cầu.

## 10. Transaction chỉ áp dụng với resource tham gia transaction

@Transactional không đồng nghĩa rollback mọi side effect.

Ví dụ trong một operation:

~~~java
@Transactional
public void recover() {
    repository.updateStatus();
    externalApi.notifyRecovery();
}
~~~

Nếu externalApi gọi một hệ thống khác không tham gia transaction, việc database rollback không tự thu hồi lời gọi mạng đã thành công. Với management operation có side effect ngoài DB, có thể cần outbox, saga/compensation, idempotency và trạng thái tác vụ.

Ngoài ra, transaction boundary chỉ hiệu lực nếu được interceptor xử lý đúng trên thread thực thi. Khi chuyển việc sang @Async hoặc executor, transaction context của thread gọi không tự động đi sang thread mới. Worker phải tự xác định transaction riêng.

## 11. Phân biệt @Async, @Transactional và proxy ordering

Một bean có thể chứa cả @Async và @Transactional. Kết quả thực tế phụ thuộc method được gọi qua proxy, thứ tự advice và thread thực thi.

Không nên giả định:

~~~java
@Async
@Transactional
public void rebuild() {}
~~~

sẽ có mọi đặc tính mong đợi mà không kiểm thử. Đặc biệt:

- Async execution chuyển sang worker thread.
- Transaction state theo thread.
- Self-invocation có thể bypass proxy.
- Exception của async method có thể không đến trực tiếp JMX caller.
- JMX client có thể nhận kết quả “đã nhận lệnh” trong khi task vẫn chạy.
- Concurrent requests cần cơ chế single-flight hoặc operation ID.

Khuyến nghị: để JMX adapter gọi một application service quản lý job, và job worker gọi transactional service qua Spring proxy được cấu hình rõ.

## 12. Security advice và quyền quản trị

Một MBean operation có thể được kiểm soát bằng Spring method security nếu lời gọi đi qua đúng proxy và security context có đủ danh tính.

Tuy nhiên, remote JMX authentication không tự động chuyển thành Spring Security Authentication trong SecurityContextHolder theo cách web request làm. Vì vậy:

- Connector JMX phải có authentication, TLS, authorization riêng.
- Không giả định @PreAuthorize sẽ thấy principal remote JMX mong muốn.
- Nếu application cần kiểm tra vai trò theo caller JMX, phải thiết kế mapping principal đáng tin cậy.
- Business service có thể áp thêm điều kiện an toàn không phụ thuộc danh tính.
- Không expose operation phá hủy dữ liệu chỉ vì nó có annotation bảo mật.

Một trường hợp nguy hiểm là JMX operation được gọi qua con đường không có security context, nhưng service dùng fallback/anonymous không được thiết kế rõ. Kiểm tra cả trường hợp được cấp quyền và bị từ chối trong integration test.

## 13. Retry và idempotency khi gọi qua proxy

MBeanProxyFactoryBean có thể khiến lời gọi từ phía Java client trông như method cục bộ:

~~~java
queueAdmin.resetStatistics();
~~~

Nhưng nếu connection là remote, lỗi mạng có thể xảy ra sau khi server đã thực thi operation. Client không thể tự suy ra lệnh chưa chạy chỉ vì nhận IOException.

Với operation có side effect, cần:

- Idempotency key khi phù hợp.
- Operation ID và trạng thái có thể truy vấn.
- Giới hạn retry.
- Không tự động retry operation nguy hiểm.
- Cơ chế reconciliation khi kết quả chưa chắc chắn.

Spring AOP retry advice nếu có cũng phải được đánh giá: tự động retry có thể làm lệnh JMX chạy hai lần và gây side effect trùng.

## 14. Transaction rollback và notification

Một management operation có thể sửa DB và phát JMX notification:

~~~text
@Transactional operation
    |
    +-- update database
    +-- send JMX notification
    +-- later exception -> rollback
~~~

Khi notification phát **trước khi transaction commit**, listener có thể nhận “đã cập nhật” dù transaction về sau rollback. JMX notification không tham gia atomic commit với database.

Một thiết kế an toàn hơn là phát tín hiệu sau commit qua transaction synchronization hoặc transactional event listener phù hợp, trong khi sự kiện bắt buộc bền vững nên dùng transactional outbox.

Cần phân biệt:

- Notification “operation started” có thể phát ngay khi bắt đầu.
- Notification “business state committed” phải phản ánh transaction đã commit.
- Notification “operation failed” cần ghi nhận nguyên nhân an toàn.
- Sự kiện được phát trước commit phải mô tả đúng semantic của nó.

Ngay cả after-commit callback cũng không bảo đảm durable delivery của notification nếu JVM chết ngay sau commit.

## 15. AOP advice làm thay đổi hiệu năng của MBean

MBean attribute thường được collector polling liên tục. Nếu getter có logging chi tiết, tracing đắt đỏ hoặc transaction advice không cần thiết, JMX polling có thể làm tăng overhead.

Ví dụ getter:

~~~java
@ManagedAttribute
@Transactional(readOnly = true)
public long getPendingCount() {
    return repository.countPending();
}
~~~

Nếu collector gọi mỗi giây trên hàng trăm instance, có thể tạo tải database. @Transactional(readOnly=true) không làm query tự trở thành nhẹ.

Nên cân nhắc snapshot/cache metric hoặc counter trong memory được cập nhật bởi nghiệp vụ, với semantic và độ trễ rõ ràng.

Cũng cần kiểm tra:

- Advice có giữ lock lâu không?
- Getter có thực hiện I/O hay side effect không?
- MBeanServer dispatch có blocked khi advice chậm không?
- Listener có làm chậm operation khi phát notification không?
- Remote collector retry có nhân lưu lượng không?

## 16. Phân biệt MBeanProxyFactoryBean với target-side AOP

Client-side typed proxy:

~~~java
MBeanProxyFactoryBean proxyFactory =
    new MBeanProxyFactoryBean();

proxyFactory.setServer(connection);
proxyFactory.setObjectName(
    "com.example.orders:type=Admin,name=payments"
);
proxyFactory.setProxyInterface(PaymentAdminClient.class);
~~~

Nó chuyển method Java thành JMX call. Proxy này không tự cấp transaction cho target MBean.

Nếu caller bọc proxy đó bằng Spring AOP, advice phía caller vẫn khác với transaction của service phía server. Trong remote setup, một transaction ở client không làm database transaction của server tự tham gia cùng một boundary.

**Transaction locality:** transaction manager và resource được quản lý ở phía JVM/thành phần thực thi nghiệp vụ; không coi remote JMX invocation là distributed transaction.

## 17. Ví dụ kiến trúc hoàn chỉnh

~~~text
Operator / Automation client
           |
           v
JMX secure connector
           |
           v
MBeanServer
           |
           v
PaymentAdmin MBean
           |
           v
PaymentMaintenanceService Spring proxy
           |
           +-- authorization / business guards
           +-- @Transactional boundary
           |
           v
Repository / scheduler / external systems
~~~

Adapter:

~~~java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Admin,name=payments"
)
public class PaymentAdmin {
    private final PaymentMaintenanceService maintenance;

    public PaymentAdmin(PaymentMaintenanceService maintenance) {
        this.maintenance = maintenance;
    }

    @ManagedOperation
    public String startReconciliation() {
        return maintenance.scheduleReconciliation();
    }
}
~~~

Service có thể tách bước schedule và bước xử lý thực tế để không giữ transaction dài trong thread JMX. Nếu scheduleReconciliation() chỉ tạo job, nó nên trả operation ID; hệ thống cần tránh gửi trùng job khi client retry.

## 18. Kiểm tra runtime class và AOP proxy

Spring có thể dùng AopUtils để nhận biết proxy:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("paymentMaintenanceService");

System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " + AopUtils.getTargetClass(bean));
~~~

Đây là kiểm tra hỗ trợ chẩn đoán, không phải bằng chứng transaction đã thực thi. Một proxy có thể được tạo cho advice khác hoặc target method không được intercept vì visibility/self-invocation.

Không log raw class names như business identity dài hạn; dùng logical ObjectName cho hợp đồng quản trị.

## 19. Kiểm tra transaction thực sự hoạt động

Trong một integration test, business service có thể quan sát:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public boolean transactionIsActive() {
    return TransactionSynchronizationManager.isActualTransactionActive();
}
~~~

Sau đó gọi operation qua MBeanServer:

~~~java
Boolean active = (Boolean) server.invoke(
    objectName,
    "checkTransaction",
    new Object[0],
    new String[0]
);
~~~

Đoạn này giả định một MBean test export operation checkTransaction() và ủy quyền tới service có method transactionIsActive(). Không phải API production được đề xuất.

Test nên assert active=true tại đúng service execution path, đồng thời có negative test với cấu hình thiếu proxy/transaction manager để xác minh test thật sự phát hiện lỗi.

Ngoài ra cần kiểm tra database rollback thật khi service ném exception, thay vì chỉ dựa vào cờ transaction active.

## 20. Integration test cho metadata và đường gọi JMX

Quy trình:

1. Tạo MBeanServer riêng bằng MBeanServerFactory.newMBeanServer().
2. Tạo Spring context với transaction manager test.
3. Tạo service @Transactional.
4. Tạo management adapter dùng service đã inject.
5. Bật exporter đúng cách.
6. Kiểm tra ObjectName đã đăng ký.
7. Đọc MBeanInfo để xác nhận method mong đợi.
8. Gọi operation qua MBeanServer.invoke.
9. Xác nhận advice chạy (transaction, tracing hoặc validation).
10. Kiểm tra exception/rollback nếu operation thất bại.
11. Đóng context, xác nhận MBean unregister.
12. Không dùng platform server chung cho parallel tests trừ khi đã cô lập tên.

### Test self-invocation

Tạo method A gọi method B trong cùng bean, B có @Transactional. So sánh với A ở adapter gọi B qua Spring-injected service proxy. Test có thể cho thấy sự khác biệt giữa lời gọi nội bộ bypass proxy và lời gọi đi qua proxy.

Điểm kiểm tra là **đường invocation thực tế**, không phải đếm annotation trong source code.

## 21. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| MBean không có operation mong đợi | Exporter nhìn proxy interface khác | Kiểm tra MBeanInfo và target |
| @Transactional không chạy | Self-invocation hoặc bypass Spring proxy | Tách transactional service |
| Getter bị chậm | Advice/database query nặng | Snapshot/metric cache |
| Operation chạy hai lần | Client/Retry advice retry không idempotent | Operation ID/idempotency |
| Method security không thấy user JMX | Principal connector không map sang Spring context | Thiết kế authorization riêng |
| Transaction rollback nhưng event đã phát | Notification trước commit | After-commit/outbox |
| Java client lỗi cast | MBean contract khác proxy interface | Đối chiếu metadata |
| ObjectName thay khi bật AOP | Naming dựa runtime proxy class | Dùng logical ObjectName |
| Khởi tạo MBean thất bại | Proxy không phù hợp interface/metadata | Kiểm tra exporter và Spring version |
| Operation dài giữ lock | Transaction bao trùm tác vụ | Async job + short transactions |
| @Async không chạy như kỳ vọng | Self-invocation/proxy ordering | Tách worker bean và test |
| Client timeout nhưng server đã làm | Remote result uncertainty | Reconcile state, tránh retry mù |

## 22. Checklist đánh giá trước production

1. JMX export có dùng đúng bean instance do Spring quản lý?
2. Bean có bị AOP proxy hay không?
3. Proxy là JDK interface-based hay class-based?
4. Method cần expose có sẵn qua interface/proxy không?
5. MBeanInfo đúng attribute/operation/signature không?
6. ObjectName có độc lập runtime proxy class không?
7. JMX operation có gọi qua transactional service proxy không?
8. Có self-invocation bypass advice không?
9. Transaction manager và resource có cấu hình đúng không?
10. Operation có I/O hoặc tác vụ dài trong transaction không?
11. @Async hoặc executor có làm mất transaction context không?
12. Method security có nhận đúng principal hay chỉ dựa vào HTTP security?
13. Remote JMX connector có auth/TLS/authorization không?
14. Retry advice có gây lệnh chạy lặp không?
15. Notification có phát trước transaction commit không?
16. Getter bị collector polling có gây tải DB không?
17. Có integration test MBeanServer.invoke và rollback không?
18. Có cleanup exporter/context sau test và shutdown không?

## 23. Bài tập thực hành

**Mục tiêu:** quan sát việc bật AOP và @Transactional thay đổi đường gọi JMX như thế nào.

### Phần A: service trực tiếp

Tạo PaymentMaintenanceService với method @Transactional ghi một bản ghi test. Export trực tiếp hoặc qua adapter, sau đó gọi qua MBeanServer và kiểm tra transaction có hoạt động.

### Phần B: self-invocation

Tạo method trigger() tự gọi method annotated trong cùng class, so sánh với lời gọi từ adapter qua service proxy. Xác định lời gọi nào có transaction active.

### Phần C: metadata

Bật JDK proxy và class-based proxy theo cấu hình test tương ứng. Đọc MBeanInfo để kiểm tra operation không biến mất khi strategy proxy thay đổi.

### Phần D: retry

Giả lập client không nhận response sau khi server đã thực hiện thao tác. Xác định tác động của retry và thiết kế operation ID.

### Phần E: notification/transaction

Phát notification trước commit và ép rollback. Sau đó thay bằng thông báo sau commit hoặc outbox để so sánh semantic.

## 24. Câu hỏi tự kiểm tra

**1. @Transactional có luôn chạy khi method được gọi qua JMX không?** Không. Điều đó phụ thuộc đường gọi có đi qua đúng Spring AOP proxy và transaction manager hay không.

**2. Vì sao self-invocation thường không áp advice?** Vì lời gọi this.method() không đi qua proxy-based interceptor.

**3. JDK proxy có thể gây khó khăn nào cho JMX metadata?** Những method không nằm trên interface proxy có thể không callable hoặc không được exporter expose như kỳ vọng.

**4. MBeanProxyFactoryBean có tự tạo transaction ở server không?** Không. Nó tạo typed client JMX proxy.

**5. Vì sao không dùng proxy class name làm ObjectName?** Tên proxy có thể đổi theo cấu hình AOP, làm mất hợp đồng client.

**6. Nếu transaction rollback, notification đã phát có tự thu hồi không?** Không. JMX notification không tham gia atomic commit.

**7. Vì sao transaction dài trong operation JMX là rủi ro?** Có thể giữ lock, connection và làm tăng timeout/độ trễ quản trị.

**8. Vì sao chỉ nhìn thấy AOP proxy không đủ kết luận transaction hoạt động?** Advice cần intercept đúng method trên đường gọi; có thể là loại advice khác.

## 25. Tổng kết

Khi rà soát ảnh hưởng của **AOP, transaction và proxy** lên Spring Framework JMX, cần kiểm tra ba lớp:

- **Export contract:** đúng ObjectName, MBeanInfo, attributes và operations dù bean bị proxy.
- **Invocation path:** lời gọi JMX thật có đi qua advice/transaction/security proxy cần thiết hay không.
- **Runtime behavior:** transaction duration, concurrency, retry, notification timing và side effect có an toàn không.

Thiết kế **management adapter mỏng gọi Spring business service proxy** thường giúp tách rõ trách nhiệm, dễ kiểm thử và giảm rủi ro expose toàn bộ service nghiệp vụ.

**JMX cho phép gọi management operation; Spring AOP chỉ áp dụng advice khi đường gọi đi qua proxy tương ứng.** Không thể dùng annotation hoặc tên class để thay thế kiểm thử đường invocation thực tế.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Declarative transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — MBeanProxyFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
