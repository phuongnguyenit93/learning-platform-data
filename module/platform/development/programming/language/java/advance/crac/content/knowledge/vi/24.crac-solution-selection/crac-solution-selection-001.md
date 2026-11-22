# CRaC và Java serialization: khác biệt về đối tượng được lưu

CRaC và Java serialization đều có thể giúp một chương trình Java tiếp tục sử dụng trạng thái đã được lưu trước đó, nhưng chúng lưu những thứ khác nhau và phục vụ hai mục tiêu khác nhau. Java serialization ghi một object graph được chọn vào byte stream. CRaC phối hợp với JVM và checkpoint engine để chụp trạng thái của cả tiến trình tại một thời điểm, sau đó khôi phục tiến trình để tiếp tục thực thi.

Vì vậy, khi dùng Java serialization, lập trình viên quyết định đối tượng gốc nào được ghi và những trường nào thuộc object graph. Khi dùng CRaC, ranh giới lưu trữ là tiến trình/JVM đang chạy: heap, trạng thái thread và nhiều trạng thái runtime được checkpoint engine hỗ trợ được lưu cùng nhau. Ứng dụng vẫn phải chuẩn bị tài nguyên bên ngoài như connection pool, socket, consumer, token và lease để chúng hợp lệ sau restore.

Điểm khác biệt này quyết định cách chọn giải pháp:

- Nếu mục tiêu là lưu một tập đối tượng nghiệp vụ hoặc trao đổi dữ liệu giữa các thành phần, serialization có thể phù hợp.
- Nếu mục tiêu là giảm thời gian khởi động bằng cách tiếp tục một ứng dụng đã khởi tạo, warm-up và nạp framework, CRaC phù hợp hơn.
- Nếu cần lưu dữ liệu lâu dài, ổn định qua nhiều phiên bản ứng dụng hoặc nhiều ngôn ngữ, nên cân nhắc định dạng dữ liệu có schema như JSON, Avro hoặc Protocol Buffers thay vì xem Java serialization là định dạng lưu trữ bền vững mặc định.

## 1. Hai cơ chế lưu trạng thái ở hai ranh giới khác nhau

### 1.1. Java serialization lưu object graph được chọn

Java serialization truyền một object graph từ một hoặc nhiều object gốc (root objects) vào một ObjectOutputStream. Stream chứa thông tin về lớp, các trường được serialize và quan hệ tham chiếu cần thiết để dựng lại graph.

Ví dụ:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(order);
}
~~~

Trong ví dụ này, order là root object. Serialization đi theo các tham chiếu từ order tới những object có thể serialize theo quy tắc của Java serialization. Nó không tự động ghi toàn bộ heap, mọi bean Spring, mọi thread hoặc mọi biến static của ứng dụng.

Thông thường, một lớp cần triển khai java.io.Serializable để tham gia cơ chế mặc định. Những trường instance không phải static và không phải transient được xét để ghi vào stream. Nếu graph chứa một đối tượng không serialize được, thao tác có thể ném NotSerializableException, trừ khi lớp tùy chỉnh xử lý trường đó bằng serialization hook hoặc loại nó khỏi trạng thái cần lưu.

### 1.2. CRaC lưu trạng thái tiến trình/JVM

CRaC (Coordinated Restore at Checkpoint) cho phép checkpoint một tiến trình Java đang chạy rồi restore tiến trình từ ảnh đã tạo. Phạm vi checkpoint do JVM, CRaC runtime và engine cụ thể phối hợp thực hiện. Với engine dựa trên CRIU, trạng thái tiến trình và hệ điều hành được dump/restore theo khả năng của kernel và CRIU; các engine khác có cách triển khai riêng.

Ảnh checkpoint thường giữ nhiều trạng thái mà Java serialization không xử lý:

- Object trong heap của JVM, không yêu cầu từng lớp nghiệp vụ phải triển khai Serializable.
- Trạng thái thực thi của các thread và stack tại điểm checkpoint, trong phạm vi engine hỗ trợ.
- Các lớp đã được nạp và trạng thái nội bộ của JVM.
- Một phần trạng thái runtime/native và process state mà engine có thể chụp.
- File descriptor, memory mapping và tài nguyên hệ điều hành theo khả năng checkpoint của engine.

Đây không phải cam kết rằng mọi socket, file, thread native hoặc kết nối bên ngoài sẽ tiếp tục hoạt động sau restore. Ứng dụng cần đăng ký resource hoặc dùng tích hợp của framework/thư viện để đóng, làm mới và tạo lại các tài nguyên không thể giữ nguyên an toàn.

### 1.3. Hình dung ranh giới lưu

~~~mermaid
flowchart TD
    subgraph SER[Java serialization]
        A[Root object] --> B[Object graph qua references]
        B --> C[Serializable fields và custom hooks]
        C --> D[Byte stream]
        D --> E[ObjectInputStream]
        E --> F[Object graph được dựng lại]
    end
    subgraph CRAC[CRaC checkpoint/restore]
        G[Ứng dụng JVM đang chạy] --> H[Resource beforeCheckpoint]
        H --> I[Checkpoint engine chụp process/JVM state]
        I --> J[Checkpoint image]
        J --> K[Restore process/JVM]
        K --> L[Resource afterRestore]
        L --> M[Ứng dụng tiếp tục thực thi]
    end
~~~

Serialization tạo một biểu diễn dữ liệu từ object graph đã chọn. CRaC tạo một ảnh trạng thái thực thi của tiến trình. Hai đầu ra không thể thay thế cho nhau.

## 2. So sánh trực tiếp

| Khía cạnh | Java serialization | CRaC |
|---|---|---|
| Đơn vị được lưu | Object graph bắt đầu từ object gốc | Trạng thái tiến trình/JVM tại checkpoint |
| Phạm vi | Những object và trường được serialization xử lý | Heap, thread/process/runtime state theo engine hỗ trợ |
| Cách chọn dữ liệu | Lập trình viên gọi writeObject() với root object | Chọn thời điểm checkpoint và chuẩn bị Resource |
| Yêu cầu lớp | Thường cần Serializable hoặc Externalizable | Không yêu cầu các lớp heap triển khai Serializable |
| Biến static | Không thuộc object state mặc định của serialization | Là một phần trạng thái class/JVM trong ảnh nếu runtime giữ được |
| Trường transient | Bị bỏ qua theo cơ chế mặc định | Vẫn nằm trong heap snapshot như các trường khác |
| Thread và stack | Không serialize thread execution state | Có thể được checkpoint/restore theo engine |
| Socket và connection | Không serialize được như một kết nối đang hoạt động | Có thể được engine xử lý một phần, nhưng thường cần callback để đóng/tạo lại kết nối |
| Điểm tiếp tục | Deserialize tạo object graph mới; ứng dụng tự quyết định tiếp tục công việc | Tiến trình tiếp tục từ trạng thái đã checkpoint |
| Tính di động | Có thể chuyển stream giữa môi trường Java tương thích lớp/schema | Ảnh thường phụ thuộc JDK build, engine, OS, kernel, CPU và runtime |
| Versioning | Phụ thuộc serialVersionUID, class evolution và custom hooks | Phụ thuộc khả năng tương thích checkpoint image của engine/runtime |
| Mục tiêu phổ biến | Lưu/trao đổi một object graph | Giảm startup bằng cách khôi phục ứng dụng đã khởi tạo |
| Quản lý tài nguyên ngoài | Ứng dụng phải tự quản lý các handle không serialize được | Ứng dụng phối hợp qua CRaC Resource hoặc integration |
| Bảo mật | Deserialize dữ liệu không tin cậy có nguy cơ gadget/deserialization attack | Checkpoint image có thể chứa secrets và trạng thái thực thi nhạy cảm |

## 3. Java serialization lưu những đối tượng nào?

### 3.1. Bắt đầu từ object gốc

Serialization không tự quét toàn bộ heap. Nó bắt đầu từ object được truyền vào writeObject() rồi đi theo các trường tham chiếu có tham gia serialization.

Ví dụ:

~~~java
import java.io.Serializable;
import java.util.List;

public final class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final CustomerSnapshot customer;
    private final List<OrderLineSnapshot> lines;

    public OrderSnapshot(
            String orderId,
            CustomerSnapshot customer,
            List<OrderLineSnapshot> lines) {
        this.orderId = orderId;
        this.customer = customer;
        this.lines = List.copyOf(lines);
    }
}
~~~

Khi ghi OrderSnapshot, serialization tiếp tục xử lý customer, các phần tử trong lines và các object tham chiếu tiếp theo nếu chúng có thể serialize. Nếu một object bắt buộc trong graph không hỗ trợ serialization và không được xử lý tùy chỉnh, việc ghi sẽ thất bại.

Vì vậy, phạm vi lưu phụ thuộc cấu trúc object graph và serialization contract của từng lớp. Thay đổi một trường tham chiếu có thể làm graph lớn hơn và khiến serialization thất bại nếu object mới không tương thích.

### 3.2. Shared reference và vòng tham chiếu

Java serialization có cơ chế handle để bảo toàn quan hệ tham chiếu trong cùng một stream. Nếu hai trường trỏ tới cùng một object, khi deserialize chúng có thể tiếp tục trỏ tới cùng một instance trong graph mới. Vòng tham chiếu cũng được hỗ trợ.

Ví dụ:

~~~java
public final class SharedCustomerReference implements Serializable {
    private static final long serialVersionUID = 1L;

    private final CustomerSnapshot billingCustomer;
    private final CustomerSnapshot shippingCustomer;

    public SharedCustomerReference(CustomerSnapshot customer) {
        this.billingCustomer = customer;
        this.shippingCustomer = customer;
    }
}
~~~

CustomerSnapshot cũng triển khai Serializable. Hai trường của SharedCustomerReference cùng giữ một tham chiếu tới object này:

~~~java
CustomerSnapshot customer = new CustomerSnapshot("C-100");
SharedCustomerReference snapshot =
        new SharedCustomerReference(customer);

try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(snapshot);
}
~~~

Trong ví dụ, SharedCustomerReference có hai trường tham chiếu cùng trỏ tới customer và các lớp trong graph đều triển khai Serializable. Khi đọc snapshot bằng ObjectInputStream, hai trường có thể tiếp tục trỏ tới cùng một instance trong graph mới. Handle table của serialization bảo toàn shared reference và hỗ trợ vòng tham chiếu trong cùng stream.

Đây là tính chất của object graph trong một stream, không có nghĩa serialization bảo toàn identity của object giữa tiến trình cũ và tiến trình mới.

### 3.3. Quy tắc static và transient

Trạng thái static thuộc lớp, không thuộc từng object instance. Java serialization mặc định không ghi các trường static như một phần trạng thái object.

Trường transient được bỏ qua trong default serialization. Sau deserialize, trường transient có thể nhận giá trị mặc định (null, 0, false) hoặc được khởi tạo lại bằng custom readObject()/logic khởi tạo của ứng dụng.

Ví dụ:

~~~java
import java.io.Serializable;

public final class UserSessionSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String userId;
    private transient String accessToken;
    private static long activeSessionCount;

    public UserSessionSnapshot(String userId, String accessToken) {
        this.userId = userId;
        this.accessToken = accessToken;
    }
}
~~~

Khi serialize object này theo mặc định:

- userId được ghi.
- accessToken bị bỏ qua vì là transient.
- activeSessionCount không được ghi như một trường của object.

Sau deserialize, ứng dụng phải cấp lại token hoặc tái tạo trạng thái transient theo chính sách. Không nên serialize credential chỉ vì trường đó đang tồn tại trong object.

Với CRaC, transient không có ý nghĩa loại trường khỏi checkpoint. Nếu object đang nằm trong heap khi checkpoint, giá trị của trường transient vẫn thuộc heap state được chụp theo cơ chế runtime. Muốn bỏ hoặc thay giá trị trước/sau restore, cần chủ động xử lý bằng callback/resource hoặc logic bootstrap.

### 3.4. Custom serialization hooks

Java serialization cho phép tùy chỉnh cách ghi/đọc object qua các phương thức như:

- private void writeObject(ObjectOutputStream out)
- private void readObject(ObjectInputStream in)
- private Object writeReplace()
- private Object readResolve()
- Externalizable.writeExternal() và readExternal()

Ví dụ:

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class UserSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String userId;
    private transient String accessToken;

    private void writeObject(ObjectOutputStream out) throws IOException {
        out.defaultWriteObject();
        // Chỉ ghi thêm dữ liệu được phép lưu theo serialization contract.
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();
        // Khôi phục trạng thái transient theo chính sách an toàn.
        accessToken = null;
    }
}
~~~

Các hook này chỉ ảnh hưởng tới Java serialization. Chúng không được gọi chỉ vì CRaC checkpoint hoặc restore diễn ra. CRaC không serialize từng object bằng ObjectOutputStream; nó checkpoint trạng thái tiến trình.

### 3.5. Lớp không triển khai Serializable

Nếu một object không triển khai Serializable xuất hiện trong graph mặc định, serialization thường ném NotSerializableException. Một lớp có thể xử lý trường đó bằng cách:

- Đánh dấu trường là transient.
- Ghi một biểu diễn thay thế trong writeObject().
- Dùng writeReplace() để thay object bằng proxy serializable.
- Triển khai Externalizable nếu muốn kiểm soát toàn bộ biểu diễn.

Với lớp con serializable có superclass không serializable, constructor không tham số của superclass không serializable được gọi khi deserialize để khởi tạo phần superclass. Những lớp trong hệ thống phức tạp vì vậy cần serialization contract rõ ràng.

CRaC không đặt yêu cầu tương tự lên lớp nghiệp vụ. Một object trong heap không cần triển khai Serializable để nằm trong checkpoint. Tuy nhiên, native resource mà object giữ có thể không khôi phục được chỉ vì object wrapper còn trong heap.

## 4. CRaC lưu những gì ngoài object graph?

### 4.1. Heap và trạng thái object

Heap là vùng chứa object đang sống của JVM. Khi checkpoint, trạng thái object hiện có được lưu cùng tiến trình theo khả năng engine. Các trường static, transient, object không triển khai Serializable và object framework đều có thể nằm trong heap snapshot.

Ví dụ, một ứng dụng Spring Boot có thể đã:

- Tạo ApplicationContext và các singleton bean.
- Bind cấu hình vào bean.
- Nạp schema, parser và metadata.
- Warm-up cache.
- Nạp class và tối ưu một số đường code.

Nếu checkpoint được tạo sau các bước này, trạng thái đã tạo có thể được giữ trong ảnh. Sau restore, ứng dụng tiếp tục từ trạng thái runtime đã lưu thay vì deserialize riêng từng bean.

### 4.2. Thread và execution state

Java serialization không lưu thread stack hoặc vị trí thực thi của thread. Một object có trường tham chiếu tới Thread không biến thread thành một phần object graph có thể tiếp tục chạy.

CRaC checkpoint tiến trình đang chạy, nên thread state và execution state là một phần của bài toán checkpoint/restore. Khả năng cụ thể phụ thuộc JVM, engine và hệ điều hành. Trước checkpoint, ứng dụng cần phối hợp để thread không mắc ở một thao tác I/O hoặc critical section không thể phục hồi.

Với worker, executor và scheduler, cần xác định:

- Thread nào có thể tiếp tục sau restore.
- Thread nào phải dừng và được tạo lại.
- Task đang chạy được hoàn tất, hủy hay retry thế nào.
- Executor đã shutdown có được thay bằng instance mới không.
- Không có hai worker xử lý cùng một công việc sau khi nhiều replica được restore.

Không coi việc thread còn tồn tại trong ảnh là bằng chứng rằng dependency hoặc công việc mà thread đang chờ vẫn còn hợp lệ.

### 4.3. Class metadata và trạng thái JVM

Java serialization lưu class descriptor và dữ liệu object cần để dựng graph. Nó không lưu một JVM đã nạp class, JIT code cache hoặc toàn bộ runtime state.

CRaC checkpoint có thể giữ trạng thái JVM như class đã nạp và các thành phần runtime mà engine hỗ trợ. Điều này giúp tránh một phần chi phí khởi động, class loading và warm-up. Tuy nhiên, mức độ giữ lại và điều kiện tương thích phụ thuộc engine/JDK; không nên giả định checkpoint image có thể chuyển tùy ý giữa các JDK build.

### 4.4. Native memory và tài nguyên hệ điều hành

Một ứng dụng Java có thể giữ trạng thái ngoài heap:

- Direct ByteBuffer.
- JNI/native library allocations.
- File descriptor và memory mapping.
- Socket và connection pool.
- Thread native và event loop.
- GPU, device hoặc tài nguyên hệ điều hành đặc thù.

Serialization chỉ ghi object graph theo contract. Nó không lưu nguyên trạng các tài nguyên native này.

CRaC engine có thể checkpoint một phần process/native state và file descriptor, nhưng tài nguyên phụ thuộc peer bên ngoài như database connection, broker session hoặc TLS session thường cần được đóng và tạo lại. Việc một object wrapper còn tồn tại không bảo đảm native handle bên trong còn dùng được.

## 5. Resource callback của CRaC và serialization hook không giống nhau

Đây là khác biệt quan trọng khi tích hợp tài nguyên bên ngoài.

### 5.1. CRaC Resource

Ứng dụng có thể triển khai org.crac.Resource để chuẩn bị trước checkpoint và phục hồi sau restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseClientResource implements Resource {
    private final DatabaseClientFactory factory;
    private DatabaseClient client;

    public DatabaseClientResource(DatabaseClientFactory factory)
            throws Exception {
        this.factory = factory;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.stopAcceptingWork();
            client.drain();
            client.close();
            client = null;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = factory.create();
        client.verifyConnection();
    }
}
~~~

DatabaseClient và DatabaseClientFactory là kiểu minh họa do ứng dụng định nghĩa. Trong thực tế, dùng lifecycle API chính thức của pool hoặc driver. Ví dụ thể hiện ý tưởng: đóng tài nguyên trước checkpoint, rồi tạo lại và xác minh sau restore.

### 5.2. Serialization hook

Một writeObject() hoặc readObject() được gọi trong quá trình ghi/đọc object stream. Nó không tự chạy khi JVM checkpoint. Nếu dùng serialization để lưu một cấu hình client, readObject() có thể tạo lại một số trường transient, nhưng đó là logic deserialize object graph.

### 5.3. Bảng phân biệt

| Cơ chế | Thời điểm gọi | Mục đích | Phạm vi |
|---|---|---|---|
| writeObject() | Khi ObjectOutputStream serialize object | Tùy chỉnh dữ liệu ghi vào stream | Một lớp/object graph |
| readObject() | Khi ObjectInputStream deserialize object | Dựng lại trạng thái object | Một lớp/object graph |
| writeReplace() | Trong serialization | Thay object bằng proxy/biểu diễn khác | Một object |
| readResolve() | Sau khi deserialize object | Thay object vừa đọc bằng instance khác | Một object |
| beforeCheckpoint() | Trước CRaC checkpoint | Quiesce, flush, close hoặc chuẩn bị resource | Resource/tiến trình |
| afterRestore() | Sau CRaC restore | Reconnect, refresh và xác minh resource | Resource/tiến trình |

Không dùng serialization hook để thay CRaC callback. Cũng không dùng CRaC callback như một cơ chế ghi object nghiệp vụ vào file.

## 6. Ví dụ: cùng một trạng thái, hai cách lưu

Giả sử ứng dụng có một object ReportModel chứa dữ liệu đã tính toán để hiển thị báo cáo.

### 6.1. Lưu object graph bằng serialization

~~~java
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

public final class ReportModel implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String reportId;
    private final List<ReportLine> lines;
    private final BigDecimal total;

    public ReportModel(
            String reportId,
            List<ReportLine> lines,
            BigDecimal total) {
        this.reportId = reportId;
        this.lines = List.copyOf(lines);
        this.total = total;
    }
}
~~~

Ghi và đọc:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(snapshotPath))) {
    out.writeObject(reportModel);
}

ReportModel restored;
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(snapshotPath))) {
    restored = (ReportModel) in.readObject();
}
~~~

Kết quả là một object graph mới được dựng từ stream. Ứng dụng cần tự quyết định khi nào đọc file, kiểm tra version dữ liệu, xử lý lỗi và đưa object vào service.

### 6.2. Lưu trạng thái ứng dụng bằng CRaC

Với CRaC, ứng dụng khởi tạo model và các bean liên quan trong heap, sau đó tạo checkpoint. Khi restore, tiến trình tiếp tục từ trạng thái đã checkpoint:

~~~java
ReportModel reportModel = reportService.prepareReport();
// Khởi tạo cache, parser và các thành phần cần thiết.
// Tới checkpoint do runtime/operator yêu cầu.
// Sau restore, ứng dụng tiếp tục sử dụng heap state đã được khôi phục.
~~~

Đoạn code trên chỉ minh họa vị trí trạng thái. Ứng dụng cần dùng CRaC runtime/engine, gọi checkpoint theo cơ chế của môi trường và đăng ký resource cho các dependency bên ngoài. Không có ObjectOutputStream nào được gọi để lưu reportModel.

### 6.3. Khi nào mỗi cách phù hợp?

Nếu chỉ cần lưu ReportModel để tải lại sau này hoặc gửi sang một process khác, serialization (hoặc định dạng dữ liệu có schema) là ranh giới phù hợp hơn.

Nếu mục tiêu là khởi động nhanh toàn bộ dịch vụ đã nạp framework, cấu hình, cache và metadata, CRaC có thể giữ trạng thái tiến trình phù hợp hơn. Dùng serialization để ghi riêng một report model không thay thế được việc khôi phục JVM, thread, bean graph và runtime state.

## 7. Khác biệt về vòng đời sau khi khôi phục

### 7.1. Deserialize là dựng object mới

ObjectInputStream.readObject() dựng object graph trong tiến trình hiện tại. Nó không đưa chương trình quay lại đúng instruction đã chạy khi ghi stream. Constructor và serialization protocol áp dụng theo quy tắc Java; đối tượng sau deserialize có identity mới so với object ở tiến trình trước, dù graph có thể bảo toàn shared reference bên trong stream.

Ứng dụng cần:

- Kiểm tra dữ liệu sau deserialize.
- Xác minh version và invariant.
- Khởi tạo lại transient state.
- Gắn object vào service hoặc repository.
- Xử lý side effect nếu việc nạp object kích hoạt hành động bổ sung.

### 7.2. Restore CRaC tiếp tục tiến trình

CRaC restore khôi phục tiến trình từ checkpoint image. Ứng dụng tiếp tục từ trạng thái runtime được lưu. Không có bước chung nào tự động gọi constructor của mọi bean hoặc deserialize lại từng object.

Các Resource callback và integration framework xử lý phần cần chuẩn bị lại. Sau restore, ứng dụng vẫn phải xác minh:

- Database và broker connection.
- Token, certificate và secret.
- Lease và leader ownership.
- DNS, endpoint và metadata của môi trường hiện tại.
- Replica identity nếu cùng ảnh được dùng cho nhiều instance.
- Cache freshness và scheduler deadline.

### 7.3. Khả năng di động

Java serialization tạo byte stream có thể được ghi vào file hoặc truyền qua network. Tuy nhiên, stream vẫn phụ thuộc class có sẵn, serialVersionUID, schema và cách các lớp xử lý class evolution. Java serialization không phải định dạng trung lập ngôn ngữ.

CRaC checkpoint image thường gắn với JDK build, engine, kernel, hệ điều hành, kiến trúc CPU, container runtime và trạng thái môi trường cụ thể. Không giả định có thể copy ảnh từ một node bất kỳ sang node khác hoặc restore bằng một bản JDK khác mà không có xác nhận tương thích.

## 8. Versioning và tương thích dữ liệu

### 8.1. serialVersionUID

Serializable class có thể khai báo serialVersionUID để kiểm soát tương thích giữa class được dùng khi ghi và class được dùng khi đọc:

~~~java
private static final long serialVersionUID = 1L;
~~~

Nếu không khai báo, Java có thể tính một giá trị mặc định dựa trên cấu trúc lớp. Thay đổi lớp có thể làm giá trị này thay đổi và gây InvalidClassException khi deserialize.

Khai báo cùng serialVersionUID không tự bảo đảm mọi thay đổi đều an toàn. Thêm/xóa trường, đổi kiểu dữ liệu, thay đổi invariant hoặc custom serialization logic vẫn cần được kiểm thử.

### 8.2. Class evolution

Với serialization, cần có chính sách:

- Trường mới có giá trị mặc định hay cần migration?
- Trường đã xóa có còn được chấp nhận khi đọc stream cũ?
- Kiểu dữ liệu có thay đổi không?
- readObject() có cần chuyển đổi dữ liệu cũ?
- Proxy serialization có giữ tương thích không?
- Có thể đọc stream từ nhiều phiên bản ứng dụng không?

Với dữ liệu cần lưu dài hạn, schema version rõ ràng và migration thường dễ quản lý hơn phụ thuộc hoàn toàn vào Java object serialization.

### 8.3. Checkpoint image evolution

CRaC image lưu trạng thái runtime, nên nâng JDK, GC, native library, agent, framework hoặc container base image có thể làm ảnh cũ không còn tương thích. Cần tạo lại checkpoint image theo pipeline đã xác minh khi nâng cấp runtime.

Không dùng serialVersionUID để giải quyết checkpoint image compatibility. Hai cơ chế có contract versioning hoàn toàn khác nhau.

## 9. Bảo mật

### 9.1. Rủi ro của Java deserialization

Không deserialize Java object stream từ nguồn không tin cậy. Object graph có thể kích hoạt hành vi trong quá trình deserialize thông qua gadget chain hoặc custom serialization hook của các lớp có trên classpath.

Nếu bắt buộc dùng Java serialization:

- Chỉ đọc stream từ nguồn tin cậy và được xác thực.
- Áp dụng ObjectInputFilter để giới hạn lớp được phép, độ sâu graph, số reference, kích thước mảng và số byte.
- Không cho phép class tùy ý chỉ vì nó triển khai Serializable.
- Kiểm tra dữ liệu sau deserialize.
- Ưu tiên format có schema và parser an toàn cho dữ liệu trao đổi bên ngoài.

Ví dụ minh họa filter theo allowlist:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "com.example.snapshot.*;java.base/*;!*");

try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(snapshotPath))) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

Filter cần được điều chỉnh theo graph thực tế. Ví dụ trên là minh họa cú pháp filter pattern; không nên sao chép nguyên trạng mà chưa kiểm tra các lớp hợp lệ và giới hạn resource.

### 9.2. Bảo vệ CRaC checkpoint image

Checkpoint image có thể chứa toàn bộ hoặc một phần lớn trạng thái memory của tiến trình, bao gồm:

- Password, access token và refresh token.
- Private key, certificate material và session secret.
- Dữ liệu người dùng hoặc payload request.
- Thông tin kết nối và cấu hình nội bộ.
- Trạng thái transaction hoặc cache nghiệp vụ.

Vì vậy:

- Chỉ tạo và restore ảnh từ pipeline/nguồn tin cậy.
- Hạn chế quyền đọc, ghi và tải checkpoint image.
- Mã hóa khi lưu trữ và truyền tải theo yêu cầu của nền tảng.
- Quản lý retention và xóa ảnh theo chính sách.
- Không đưa image vào registry công khai.
- Không log nội dung nhạy cảm từ heap hoặc resource callback.
- Làm mới credential sau restore khi có thể hết hạn hoặc bị rotate.

Serialization stream và CRaC image đều cần được bảo vệ, nhưng bề mặt dữ liệu khác nhau. Một stream có thể chỉ chứa một object graph; checkpoint image có thể chứa trạng thái rộng hơn nhiều của ứng dụng.

## 10. Hiệu năng và chi phí

### 10.1. Java serialization

Chi phí phụ thuộc kích thước object graph, số object, số tham chiếu, custom hooks, I/O và việc cấp phát object khi deserialize. Ưu điểm là có thể chỉ lưu phần dữ liệu cần thiết. Nếu graph nhỏ và có cấu trúc rõ, việc ghi/đọc một số object có thể đơn giản hơn checkpoint toàn tiến trình.

Nhược điểm là ứng dụng phải chọn đúng graph, xử lý class compatibility, khôi phục transient state và tích hợp object trở lại vòng đời ứng dụng.

### 10.2. CRaC

Chi phí checkpoint/restore phụ thuộc kích thước memory, số thread, số mapping, số resource, checkpoint engine và môi trường hệ điều hành. Một ảnh lớn có thể tốn dung lượng lưu trữ, thời gian copy và thời gian restore.

Ưu điểm là giữ lại trạng thái đã khởi tạo ở cấp tiến trình, có thể giảm đáng kể công việc lặp lại khi khởi động. Nhược điểm là image phụ thuộc runtime/môi trường và các tài nguyên ngoài vẫn cần xử lý.

### 10.3. Không so sánh hai cơ chế chỉ bằng thời gian ghi file

Một phép đo công bằng cần tính toàn bộ công việc:

| Đại lượng | Serialization | CRaC |
|---|---|---|
| Thời gian tạo snapshot | Ghi object graph ra stream | Tạo checkpoint process image |
| Dung lượng | Kích thước object graph đã serialize | Kích thước checkpoint image |
| Thời gian khôi phục | Deserialize và tích hợp object vào app | Restore process/JVM và phục hồi resource |
| Công việc bổ sung | Reinitialize transient state, validate graph | Reconnect, refresh credential, readiness |
| Phạm vi được khôi phục | Object graph đã chọn | Trạng thái tiến trình theo engine |

Nếu mục tiêu là startup time, hãy đo restore-to-ready và first-request latency của CRaC. Nếu mục tiêu là tải một tập dữ liệu, hãy đo thời gian deserialize, validate và đưa graph vào sử dụng. Không lấy thời gian ghi một object nhỏ so với thời gian tạo ảnh toàn JVM để kết luận cơ chế nào nhanh hơn nói chung.

## 11. Chọn giải pháp theo bài toán

### 11.1. Chọn Java serialization khi

- Cần lưu một object graph cụ thể.
- Các lớp có serialization contract rõ ràng.
- Dữ liệu cần được ghi/đọc như một stream.
- Không cần khôi phục thread, JVM hoặc tiến trình đang thực thi.
- Ứng dụng có thể tự khởi tạo lại resource và trạng thái runtime.
- Nguồn stream tin cậy và có chính sách version/filter phù hợp.

Java serialization thường phù hợp với dữ liệu nội bộ có phạm vi kiểm soát. Với lưu trữ lâu dài hoặc giao tiếp giữa hệ thống khác ngôn ngữ, hãy cân nhắc JSON, Avro, Protobuf hoặc định dạng schema khác.

### 11.2. Chọn CRaC khi

- Cần giảm thời gian khởi động một ứng dụng Java đã khởi tạo.
- Chi phí lớn nằm ở framework startup, class loading, warm-up hoặc nạp dữ liệu trong heap.
- Muốn tiếp tục trạng thái runtime của cả tiến trình.
- Có JDK/engine và môi trường triển khai hỗ trợ checkpoint/restore.
- Có thể chuẩn bị và phục hồi tài nguyên ngoài bằng CRaC Resource hoặc integration.
- Có quy trình bảo vệ, tạo, phân phối và kiểm thử checkpoint image.

### 11.3. Dùng kết hợp khi

Hai cơ chế có thể cùng xuất hiện trong một ứng dụng vì chúng giải quyết hai ranh giới khác nhau:

- Serialization lưu một phần dữ liệu nghiệp vụ bền vững hoặc trao đổi giữa hệ thống.
- CRaC giữ trạng thái tiến trình đã khởi tạo để giảm startup.

Ví dụ, một ứng dụng có thể đọc một snapshot dữ liệu từ format có schema, tạo cache trong heap, rồi tạo CRaC checkpoint để nhân bản môi trường đã warm-up. Sau restore, ứng dụng vẫn cần xác minh cache freshness và kết nối. Không cần serialize toàn bộ bean graph chỉ để tạo checkpoint.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| CRaC là Java serialization ở cấp JVM | CRaC checkpoint tiến trình/JVM bằng runtime engine; không ghi từng object bằng ObjectOutputStream |
| Mọi object phải triển khai Serializable để được CRaC lưu | CRaC không yêu cầu serialization contract của từng lớp |
| Java serialization lưu toàn bộ heap | Nó lưu object graph từ root object được chọn và các thành phần theo serialization rules |
| Trường transient không có trong CRaC image | transient chỉ ảnh hưởng Java serialization mặc định; giá trị vẫn nằm trong heap checkpoint nếu còn trong memory |
| Biến static được ghi vào serialization stream | Static thuộc class state và không được ghi như trường instance mặc định |
| Deserialize tiếp tục thread đang chạy | Deserialize dựng object graph; nó không khôi phục vị trí thực thi của thread |
| CRaC bảo đảm mọi socket và database connection vẫn hoạt động | Resource bên ngoài thường cần đóng, làm mới hoặc tạo lại |
| readObject được gọi sau CRaC restore | Serialization hook không tự chạy trong CRaC lifecycle |
| serialVersionUID quyết định checkpoint compatibility | Nó chỉ thuộc Java serialization; checkpoint image phụ thuộc JDK/engine/OS/runtime |
| Checkpoint image có thể di chuyển tự do giữa máy | Tính di động phụ thuộc engine và môi trường tương thích |
| Một stream serialization luôn an toàn nếu lớp implements Serializable | Deserialize dữ liệu không tin cậy có thể dẫn tới gadget/deserialization attack |
| Checkpoint image chỉ chứa dữ liệu không nhạy cảm | Heap/process state có thể chứa credential và dữ liệu người dùng |

## 13. Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là có | Hướng phù hợp |
|---|---|---|
| Chỉ cần lưu một object hoặc một graph nhỏ? | Có | Serialization hoặc format dữ liệu có schema |
| Cần giữ trạng thái nhiều bean/framework đã khởi tạo? | Có | CRaC |
| Cần tiếp tục thread và tiến trình từ điểm checkpoint? | Có | CRaC |
| Cần trao đổi dữ liệu với hệ thống không chạy Java? | Có | JSON/Avro/Protobuf thường phù hợp hơn Java serialization |
| Cần snapshot ứng dụng để giảm startup? | Có | CRaC |
| Cần lưu dữ liệu lâu dài qua nhiều phiên bản? | Có | Format có schema và migration rõ ràng |
| Cần giữ connection database sống qua thời gian dừng? | Có | Không dựa vào serialization; với CRaC phải thiết kế Resource để reconnect |
| Cần kiểm soát chính xác trường nào được lưu? | Có | Serialization hoặc format dữ liệu có schema |
| Cần phục hồi toàn bộ trạng thái process/JVM? | Có | CRaC |

## 14. Quy trình thiết kế khi chọn Java serialization

1. Chọn root object và xác định graph cần lưu.
2. Đánh giá mọi trường tham chiếu và lớp trong graph.
3. Khai báo serialVersionUID và chính sách class evolution.
4. Đánh dấu transient cho trạng thái không nên ghi.
5. Viết custom serialization hook khi cần biểu diễn thay thế.
6. Xác định cách tái tạo transient state sau deserialize.
7. Thêm ObjectInputFilter và chỉ đọc stream từ nguồn tin cậy.
8. Kiểm thử stream từ phiên bản cũ và các thay đổi class.
9. Xác minh invariant sau khi object graph được dựng lại.
10. Đo thời gian ghi/đọc, kích thước stream và chi phí tích hợp.

## 15. Quy trình thiết kế khi chọn CRaC

1. Xác nhận JDK/runtime và checkpoint engine hỗ trợ CRaC.
2. Chọn thời điểm checkpoint sau khi các bước khởi tạo có thể tái sử dụng hoàn tất.
3. Liệt kê mọi resource ngoài heap: socket, pool, consumer, scheduler, file, native handle.
4. Đăng ký org.crac.Resource hoặc dùng integration framework phù hợp.
5. Dừng nhận việc mới, drain task và đóng tài nguyên trước checkpoint.
6. Tạo checkpoint image và ghi lại runtime/image metadata.
7. Restore trên môi trường tương thích.
8. Tạo lại kết nối, credential, identity và lease sau restore.
9. Xác minh dependency và readiness trước khi nhận traffic.
10. Kiểm thử restore nhiều lần và nhiều replica nếu image dùng để scale-out.
11. Bảo vệ checkpoint image như dữ liệu chứa trạng thái memory nhạy cảm.
12. Đo restore-to-ready, first-request latency, p50/p95/p99 và throughput.

## 16. Nguyên tắc cần nhớ

- Java serialization lưu object graph được chọn; CRaC lưu trạng thái tiến trình/JVM theo khả năng của checkpoint engine.
- Serialization bắt đầu từ root object và đi theo tham chiếu; nó không tự ghi toàn bộ heap.
- Serializable, transient, serialVersionUID và serialization hooks thuộc Java serialization.
- CRaC không yêu cầu mọi lớp triển khai Serializable; trường transient và static vẫn là trạng thái JVM/heap theo phạm vi checkpoint.
- Serialization không lưu thread execution state; CRaC có thể khôi phục thread/process state theo engine.
- Không giả định CRaC giữ nguyên mọi socket, database connection hoặc native resource; cần Resource callback và integration.
- writeObject()/readObject() không thay thế beforeCheckpoint()/afterRestore().
- Java serialization dựng object graph mới; CRaC tiếp tục tiến trình từ trạng thái checkpoint.
- Serialization stream phụ thuộc class compatibility; checkpoint image phụ thuộc JDK, engine và môi trường runtime.
- Không deserialize dữ liệu không tin cậy; dùng filter và format có schema khi phù hợp.
- Bảo vệ checkpoint image vì heap/process state có thể chứa secrets và dữ liệu người dùng.
- Chọn theo ranh giới cần lưu: dữ liệu/object graph hay toàn bộ tiến trình đã khởi tạo.

Java serialization và CRaC không phải hai phiên bản của cùng một kỹ thuật. Serialization lưu một phần dữ liệu được chọn theo object graph và serialization contract của lớp. CRaC lưu trạng thái thực thi của một tiến trình Java để có thể tiếp tục sau restore, đồng thời yêu cầu ứng dụng phối hợp với các tài nguyên bên ngoài. Khi xác định rõ phạm vi trạng thái cần giữ, khả năng tương thích và vòng đời tài nguyên, việc chọn đúng cơ chế sẽ đơn giản và ít rủi ro hơn.
