# Tham chiếu yếu trong Context và cách giữ Resource còn tồn tại

Trong CRaC, ứng dụng đăng ký một đối tượng triển khai `Resource` với `Context` để JVM gọi các callback trước checkpoint và sau restore. Một chi tiết quan trọng là việc đăng ký không nên được hiểu là ứng dụng đã chuyển quyền sở hữu vòng đời của đối tượng cho `Context`. Trong triển khai CRaC sử dụng tham chiếu yếu để lưu đăng ký, `Context` có thể nhận biết một `Resource` khi đối tượng còn sống, nhưng tham chiếu đó không ngăn Garbage Collector thu hồi đối tượng.

Vì vậy, ứng dụng phải giữ một **strong reference** đến từng `Resource` trong suốt khoảng thời gian cần callback. Nếu chỉ tạo đối tượng rồi gọi `register()` mà không giữ nó ở một field, collection hoặc một chủ sở hữu sống lâu, đối tượng có thể trở nên unreachable và bị GC thu hồi trước khi checkpoint. Khi đó callback mà ứng dụng mong đợi có thể không được gọi.

## 1. Context, Resource và vòng đời đối tượng

`Resource` đại diện cho một tài nguyên hoặc một thành phần cần chuẩn bị trước checkpoint và phục hồi sau restore. Ví dụ: connection pool, socket do ứng dụng quản lý, thread nền, cache có trạng thái cần đồng bộ hoặc một thành phần tích hợp với thư viện native.

`Context` là nơi đăng ký và hủy đăng ký các `Resource`. Với CRaC API, ứng dụng thường đăng ký vào global context thông qua `Core.getGlobalContext()` hoặc một context phù hợp do ứng dụng quản lý.

Một `Resource` thường triển khai hai callback:

- `beforeCheckpoint(...)`: chuẩn bị tài nguyên trước khi JVM tạo ảnh trạng thái. Ví dụ hoàn tất công việc đang chạy, đóng hoặc tạm dừng kết nối cần được tạo lại sau restore, và đưa tài nguyên về trạng thái an toàn.
- `afterRestore(...)`: phục hồi hoặc kiểm tra tài nguyên khi tiến trình được khôi phục. Ví dụ mở lại kết nối, tạo lại pool hoặc khởi động lại tác vụ nền.

Việc gọi `Context.register(resource)` đăng ký đối tượng với lifecycle CRaC. Tuy nhiên, trong cách triển khai dùng weak reference, đăng ký này không tạo ra một đường tham chiếu mạnh từ GC root đến `resource`.

## 2. Strong reference và WeakReference khác nhau thế nào?

Garbage Collector xác định object còn sống dựa trên khả năng truy cập từ các GC root như biến static đang được sử dụng, stack của thread đang hoạt động và các object còn reachable từ những root đó.

| Loại tham chiếu | Ý nghĩa đối với GC | Tác động đến Resource |
| --- | --- | --- |
| Strong reference | Giữ object reachable; GC không thu hồi object chỉ vì nó còn được tham chiếu mạnh | Field hoặc collection của một owner còn sống có thể giữ `Resource` tồn tại. |
| Weak reference | Không giữ object sống; referent có thể bị thu hồi khi không còn strong reference | Nếu `Context` chỉ giữ weak reference, đăng ký không bảo đảm `Resource` còn tồn tại. |
| Soft reference | Cho phép GC thu hồi object khi cần bộ nhớ; thời điểm thu hồi không phù hợp để quản lý lifecycle bắt buộc | Không dùng làm cơ chế bảo đảm callback CRaC được gọi. |
| Phantom reference | Dùng cho cơ chế theo dõi sau khi object đã trở nên phantom reachable, thường kết hợp `ReferenceQueue` | Không dùng để giữ `Resource` sống cho callback. |

Ví dụ về một weak reference thông thường trong Java:

```java
Resource resource = new MyResource();
WeakReference<Resource> weak = new WeakReference<>(resource);

// Strong reference vẫn còn nên resource vẫn reachable.
System.out.println(weak.get());

resource = null;
// Nếu không còn strong reference nào khác, GC có thể thu hồi object.
// Sau khi bị thu hồi, weak.get() trả về null.
```

Weak reference chỉ cho phép quan sát object nếu nó còn tồn tại. Nó không thay thế việc sở hữu và quản lý vòng đời object.

## 3. Vì sao Resource có thể bị GC thu hồi sau khi register?

Xem ví dụ sau:

```java
void registerResource() {
    MyResource resource = new MyResource();
    Core.getGlobalContext().register(resource);
}
```

Biến `resource` chỉ là biến cục bộ. Khi phương thức kết thúc, ứng dụng không còn giữ strong reference nào qua biến này. Nếu `Context` chỉ giữ weak reference, đối tượng có thể bị GC thu hồi trước thời điểm checkpoint.

Một dạng ngắn hơn cũng có vấn đề tương tự:

```java
Core.getGlobalContext().register(new MyResource());
```

Đối tượng được tạo và đăng ký, nhưng không được lưu vào một owner có vòng đời đủ dài. Việc lời gọi `register()` hoàn tất không có nghĩa object sẽ tiếp tục tồn tại đến lúc CRaC gọi callback.

Một collection chỉ chứa weak reference cũng không giải quyết được vấn đề:

```java
private final List<WeakReference<Resource>> resources = new ArrayList<>();
```

Collection này chỉ giữ các wrapper `WeakReference`, không giữ mạnh các `Resource` được tham chiếu. Khi cần bảo đảm Resource tồn tại, collection quản lý phải giữ trực tiếp object bằng strong reference.

## 4. Giữ Resource bằng field của một owner sống lâu

Cách đơn giản là lưu `Resource` vào field của một đối tượng có vòng đời ít nhất bằng khoảng thời gian đăng ký. Owner phải tự nó còn reachable từ application context hoặc một GC root khác.

Ví dụ một owner giữ tài nguyên CRaC:

```java
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceOwner {
    private final MyResource resource;

    public CracResourceOwner(MyDependency dependency) {
        this.resource = new MyResource(dependency);
        Core.getGlobalContext().register(this.resource);
    }
}
```

Field `resource` tạo ra strong reference từ `CracResourceOwner` đến `MyResource`. Khi owner còn sống, Resource cũng còn reachable.

Tuy nhiên, chỉ có field là chưa đủ nếu chính `CracResourceOwner` cũng không được giữ lại. Ví dụ tạo owner trong một phương thức rồi bỏ đi mà không lưu owner ở đâu vẫn có thể khiến cả owner và Resource bị thu hồi. Chuỗi tham chiếu phải có một điểm bắt đầu còn sống:

```text
Spring ApplicationContext / application root
                  |
                  | strong reference
                  v
          CracResourceOwner
                  |
                  | strong reference (field)
                  v
             MyResource
                  |
                  | weak registration
                  v
              Context
```

Trong ứng dụng Spring, một bean singleton được Spring `ApplicationContext` quản lý thường là owner phù hợp, miễn là bean đó được tạo và giữ trong suốt thời gian cần CRaC callbacks.

## 5. Ví dụ với Spring singleton bean

Ví dụ sau minh họa một bean giữ `Resource` bằng field. Bean singleton được Spring container quản lý nên owner và Resource có thể tồn tại xuyên suốt vòng đời ứng dụng.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;
import javax.sql.DataSource;

@Component
public class CracResourceRegistration {
    private final DatabaseResource databaseResource;

    public CracResourceRegistration(DataSource dataSource) {
        this.databaseResource = new DatabaseResource(dataSource);
        Core.getGlobalContext().register(this.databaseResource);
    }
}

final class DatabaseResource implements Resource {
    private final DataSource dataSource;

    DatabaseResource(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) throws Exception {
        // Chuẩn bị các kết nối/tài nguyên do ứng dụng quản lý.
        // Cách xử lý cụ thể phụ thuộc loại DataSource và pool đang dùng.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) throws Exception {
        // Kiểm tra hoặc khởi tạo lại tài nguyên cần dùng sau restore.
        // Không giả định connection cũ luôn còn hợp lệ.
    }
}
```

Ví dụ tập trung vào quan hệ tham chiếu. Phần đóng/mở connection pool cần được triển khai theo API của pool cụ thể; không nên đóng một `DataSource` rồi giả định nó có thể khởi động lại nếu implementation không hỗ trợ thao tác đó.

Một số lưu ý:

- Spring mặc định quản lý bean theo scope singleton nếu không khai báo scope khác.
- Bean owner phải thực sự được component scan hoặc được khai báo trong cấu hình để Spring tạo và giữ nó.
- Không tạo bean owner theo prototype rồi bỏ reference sau khi khởi tạo.
- Nếu owner bị hủy trong quá trình shutdown hoặc application context đóng, cần đồng bộ việc unregister với vòng đời tài nguyên.
- Dependency được Resource giữ qua field cũng cần còn hợp lệ theo lifecycle của nó; giữ Resource sống không tự động làm một socket hay database connection trở nên hợp lệ sau restore.

## 6. Quản lý nhiều Resource bằng registry

Khi ứng dụng có nhiều tài nguyên được tạo động, có thể tạo một registry chịu trách nhiệm đăng ký và giữ strong reference đến các Resource đang hoạt động.

```java
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Component
public class CracResourceRegistry {
    private final List<Resource> resources = new ArrayList<>();

    public synchronized void register(Resource resource) {
        Objects.requireNonNull(resource, "resource");
        Core.getGlobalContext().register(resource);
        resources.add(resource);
    }

    public synchronized void unregister(Resource resource) {
        Core.getGlobalContext().unregister(resource);
        resources.remove(resource);
    }
}
```

Trong ví dụ này, `resources` giữ strong reference đến từng Resource. Registry là bean singleton nên Spring container giữ registry sống. Khi cần hủy đăng ký, gọi `unregister()` trên Context và sau đó xóa strong reference trong registry.

Thứ tự thao tác cần phản ánh lifecycle thực tế:

1. Tạo Resource và chuẩn bị dependency của nó.
2. Đăng ký Resource với Context.
3. Giữ Resource trong registry trong toàn bộ thời gian nó cần tham gia checkpoint/restore.
4. Khi tài nguyên kết thúc vòng đời và không cần callback nữa, unregister khỏi Context.
5. Sau khi unregister hoàn tất, loại bỏ strong reference để GC có thể thu hồi object khi không còn owner khác.

Registry mẫu dùng `List` để minh họa. Trong ứng dụng có đăng ký/hủy đăng ký đồng thời, cần thiết kế đồng bộ phù hợp với concurrency và lifecycle của ứng dụng. Cũng cần quyết định cách xử lý đăng ký trùng lặp, lỗi khi register/unregister và việc dọn Resource khi khởi tạo chỉ hoàn tất một phần.

## 7. Khi nào nên unregister và giải phóng Resource?

Giữ strong reference là cần thiết trong khoảng thời gian Resource cần tham gia CRaC lifecycle. Điều đó không có nghĩa phải giữ tất cả Resource mãi mãi.

Ví dụ, một kết nối tạm thời được tạo cho một job có vòng đời ngắn. Khi job kết thúc và tài nguyên không còn cần được CRaC quản lý, ứng dụng nên:

1. Đảm bảo không còn callback hoặc công việc nào đang sử dụng Resource.
2. Gọi `Context.unregister(resource)` theo API đang dùng.
3. Loại bỏ Resource khỏi registry/owner.
4. Giải phóng các dependency mà Resource sở hữu theo quy tắc của chúng.

Không nên xóa Resource khỏi collection trước khi unregister nếu việc đó làm mất strong reference trong lúc Context vẫn cần quản lý nó. Ngược lại, không unregister quá sớm khi ứng dụng vẫn cần callback trước checkpoint hoặc sau restore.

Nếu Resource chỉ cần tồn tại trong toàn bộ vòng đời ứng dụng, một owner singleton hoặc một field trong application service có thể là lựa chọn đơn giản. Với tài nguyên động, registry có lifecycle rõ ràng sẽ dễ kiểm soát hơn.

## 8. Các cách giữ Resource không hiệu quả

| Cách làm | Vì sao không bảo đảm Resource còn sống |
| --- | --- |
| Chỉ gọi `Context.register(new MyResource())` | Không có strong reference được lưu ở phía ứng dụng. |
| Lưu `WeakReference<Resource>` trong field | Field chỉ giữ wrapper weak reference, không giữ referent sống. |
| Đưa Resource làm key trong `WeakHashMap` | Key được giữ yếu nên có thể bị GC thu hồi. |
| Chỉ giữ Resource trong biến local của phương thức khởi tạo | Khi phương thức kết thúc và không còn strong path khác, object có thể unreachable. |
| Dựa vào `System.gc()` để kiểm tra hoặc giữ object | `System.gc()` chỉ là yêu cầu/hint; không bảo đảm thời điểm hoặc kết quả GC. |
| Giữ Resource trong cache có eviction | Cache có thể tự loại bỏ entry trước khi checkpoint diễn ra. |
| Giữ Resource trong một owner cũng không còn reachable | Cả owner và Resource có thể cùng bị thu hồi nếu không có strong path từ GC root. |

Một `static final` field có thể giữ Resource mạnh, nhưng cần cân nhắc lifecycle của classloader và thứ tự khởi tạo. Trong ứng dụng Spring, bean singleton hoặc registry do container quản lý thường thể hiện rõ hơn quyền sở hữu và dependency.

## 9. Cách chẩn đoán khi callback không được gọi

Nếu ứng dụng kỳ vọng một Resource được callback nhưng không thấy callback tương ứng, cần kiểm tra cả đăng ký lẫn reachability.

### Kiểm tra nơi tạo Resource

Tìm tất cả vị trí tạo đối tượng và xác định sau lệnh `register()` còn owner nào giữ strong reference hay không. Đặc biệt chú ý các trường hợp tạo object inline, biến local, callback lambda hoặc anonymous class được tạo tạm thời.

### Kiểm tra owner

Nếu Resource nằm trong field, xác nhận owner vẫn được quản lý trong suốt vòng đời ứng dụng. Với Spring, kiểm tra bean có được khởi tạo, có scope phù hợp và có bị hủy sớm hay không.

### Kiểm tra registry

Nếu dùng registry, xác nhận registry lưu trực tiếp `Resource` trong collection mạnh như `List` hoặc `Set` phù hợp. Kiểm tra không có code path nào xóa Resource hoặc unregister trước thời điểm checkpoint.

### Quan sát GC và heap

Có thể dùng heap dump, debugger hoặc công cụ quan sát reference để xem Resource còn reachable hay không. Nếu dùng `WeakReference` trong một phép chẩn đoán, có thể quan sát `weakReference.get()` để biết referent còn tồn tại tại thời điểm kiểm tra. Không nên dùng `System.gc()` làm bằng chứng duy nhất vì GC không bắt buộc phải chạy ngay khi được yêu cầu.

### Kiểm tra log callback

Ghi log khi đăng ký, khi bắt đầu/kết thúc `beforeCheckpoint`, khi bắt đầu/kết thúc `afterRestore`, và khi unregister. Log nên có tên Resource hoặc định danh ổn định để phân biệt các instance. Tránh chỉ log `toString()` nếu implementation không tạo định danh dễ truy vết.

Ví dụ log ở mức khái niệm:

```text
resource=database-pool event=registered
resource=database-pool event=beforeCheckpoint-start
resource=database-pool event=beforeCheckpoint-complete
resource=database-pool event=afterRestore-start
resource=database-pool event=afterRestore-complete
```

Nếu log `registered` xuất hiện nhưng callback không xuất hiện, kiểm tra reachability, việc unregister, loại Context và log của runtime. Bản thân log đăng ký chỉ chứng minh code đã gọi `register()`, không chứng minh object vẫn còn sống đến lúc callback.

## 10. Kiểm thử vòng đời Resource

Một kiểm thử hữu ích cần chứng minh owner giữ Resource trong suốt vòng đời cần thiết và callback vẫn có thể được gọi khi thực hiện checkpoint/restore trong môi trường CRaC thực tế.

Có thể tổ chức kiểm thử theo các bước:

1. Tạo owner và Resource.
2. Đăng ký Resource với Context.
3. Xác nhận owner lưu Resource bằng strong reference.
4. Chạy ứng dụng đủ lâu hoặc tạo áp lực bộ nhớ trong môi trường thử nghiệm để quan sát rằng Resource vẫn được giữ bởi owner.
5. Thực hiện checkpoint bằng cơ chế CRaC của runtime.
6. Xác nhận `beforeCheckpoint` được gọi.
7. Restore và xác nhận `afterRestore` được gọi.
8. Unregister Resource khi vòng đời kết thúc và xác nhận registry giải phóng reference.

Không nên viết kiểm thử phụ thuộc vào việc `System.gc()` phải thu hồi một object đúng thời điểm. GC có quyền trì hoãn collection. Có thể dùng `WeakReference` và `ReferenceQueue` trong kiểm thử chuyên biệt để quan sát khả năng thu hồi, nhưng kiểm thử lifecycle cuối cùng vẫn phải chạy trên JDK/CRaC và môi trường checkpoint/restore mà ứng dụng hỗ trợ.

Ngoài ra, không nên kiểm thử chỉ bằng cách gọi trực tiếp hai callback rồi kết luận CRaC hoạt động đúng. Gọi trực tiếp callback có thể kiểm tra logic nội bộ của Resource, nhưng không xác nhận được Context registration, khả năng lưu ảnh hoặc restore thực tế.

## 11. Checklist khi triển khai Resource

- [ ] Mỗi Resource được tạo và đăng ký đúng một lần theo thiết kế lifecycle.
- [ ] Có một owner còn sống giữ strong reference đến Resource.
- [ ] Owner được giữ bởi Spring container hoặc application root trong toàn bộ khoảng thời gian cần callback.
- [ ] Không chỉ dựa vào weak reference, `WeakHashMap`, cache eviction hoặc biến local.
- [ ] `beforeCheckpoint` chuẩn bị tài nguyên và xử lý lỗi có chủ đích.
- [ ] `afterRestore` khôi phục hoặc kiểm tra các tài nguyên cần thiết.
- [ ] Resource chỉ được unregister khi không còn cần tham gia CRaC lifecycle.
- [ ] Sau unregister, registry loại bỏ strong reference để tránh giữ object không cần thiết.
- [ ] Có log nhận diện Resource ở thời điểm register, callback và unregister.
- [ ] Đã kiểm thử checkpoint/restore bằng đúng JDK CRaC và môi trường triển khai dự kiến.

## 12. Kết luận

Đăng ký một `Resource` với `Context` không nên được xem là bảo đảm rằng object sẽ tồn tại đến lúc checkpoint hoặc restore. Khi Context dùng weak reference, GC vẫn có thể thu hồi Resource nếu ứng dụng không giữ strong reference ở nơi khác.

Hãy để một owner có vòng đời đủ dài giữ Resource bằng field hoặc collection mạnh. Trong ứng dụng Spring, một singleton bean hoặc registry do `ApplicationContext` quản lý thường phù hợp. Khi tài nguyên kết thúc vòng đời, unregister trước rồi mới giải phóng strong reference. Quản lý rõ ràng chuỗi tham chiếu và lifecycle như vậy giúp các callback CRaC được thực hiện trên đúng Resource mà ứng dụng dự kiến.
