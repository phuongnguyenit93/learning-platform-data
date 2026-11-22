# API CRaC và dịch vụ snapshot được quản lý như AWS Lambda SnapStart

CRaC và AWS Lambda SnapStart đều dùng ý tưởng chụp trạng thái một tiến trình đã khởi tạo để giảm công việc phải lặp lại khi khởi động. Tuy nhiên, hai lựa chọn này nằm ở hai lớp khác nhau. CRaC cung cấp API và cơ chế tích hợp để ứng dụng phối hợp vòng đời tài nguyên quanh checkpoint/restore; đội phát triển và vận hành thường kiểm soát nhiều phần của runtime, checkpoint và hạ tầng. Lambda SnapStart là tính năng snapshot được AWS quản lý cho các Lambda function version và runtime được hỗ trợ; dịch vụ đảm nhiệm việc tạo, lưu và phục hồi snapshot trong môi trường Lambda.

Vì vậy, không nên xem SnapStart là một checkpoint engine CRaC tổng quát hoặc giả định một checkpoint tạo bằng CRaC có thể đưa trực tiếp vào Lambda. Cách chọn phù hợp phụ thuộc vào nơi ứng dụng chạy, mức độ kiểm soát hạ tầng cần thiết, mô hình triển khai, yêu cầu cold start, khả năng quản lý tài nguyên và chi phí vận hành.

## 1. Hai lựa chọn giải quyết cùng một vấn đề ở hai lớp khác nhau

Một ứng dụng Java thường mất thời gian khởi động để nạp class, tạo object, khởi tạo framework, đọc cấu hình, thiết lập kết nối và làm nóng một phần code. Khi cần tạo nhiều instance, những bước lặp lại này có thể làm tăng latency khởi động.

Checkpoint/snapshot cho phép chuẩn bị một trạng thái đã khởi tạo rồi dùng trạng thái đó để bắt đầu các instance mới nhanh hơn. Điểm khác nhau là ai sở hữu quá trình snapshot và ứng dụng có thể kiểm soát những gì.

~~~text
                 Ứng dụng Java
                      |
           Khởi tạo framework và dependency
                      |
          Chuẩn bị tài nguyên trước snapshot
                      |
             +--------+--------+
             |                 |
             v                 v
         API CRaC          Lambda SnapStart
             |                 |
     JDK/runtime tích hợp   Lambda runtime được hỗ trợ
             |                 |
     Checkpoint engine      AWS quản lý snapshot
     và hạ tầng do đội      của published function version
     triển khai lựa chọn          |
             |                 |
     Đội vận hành điều      Lambda restore execution
     phối checkpoint/restore environment khi cần
             |                 |
             +--------+--------+
                      |
              Ứng dụng tiếp tục
               sau khi phục hồi
~~~

CRaC mô tả cách ứng dụng phối hợp với runtime thông qua Resource lifecycle. SnapStart mô tả một tính năng managed của AWS Lambda, trong đó snapshot lifecycle được gắn với quá trình publish và chạy Lambda function version. SnapStart có thể sử dụng các hook tương thích CRaC trong Java runtime để ứng dụng chuẩn bị hoặc phục hồi tài nguyên, nhưng quyền sở hữu snapshot vẫn thuộc dịch vụ Lambda.

## 2. CRaC API là gì?

CRaC là viết tắt của Coordinated Restore at Checkpoint. Dự án CRaC cung cấp API Java để ứng dụng thông báo cho runtime cách chuẩn bị tài nguyên trước checkpoint và phục hồi chúng sau restore.

API phổ biến xoay quanh interface **org.crac.Resource**:

- **beforeCheckpoint(...)**: runtime gọi trước khi tạo checkpoint để Resource đóng, flush, tạm dừng hoặc lưu trạng thái cần thiết.
- **afterRestore(...)**: runtime gọi sau khi tiến trình được restore để Resource tạo lại hoặc xác minh tài nguyên.
- **Core.getGlobalContext().register(resource)**: đăng ký Resource với context toàn cục để runtime điều phối callback.

CRaC API không phải một lệnh Java chuẩn thuộc Java SE mà mọi JDK đều phải cung cấp. Cần chọn JDK distribution/runtime có hỗ trợ CRaC và kiểm tra tài liệu của phiên bản đó. API, runtime integration, checkpoint engine và giới hạn nền tảng phải được xét cùng nhau.

### Ví dụ Resource đơn giản

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;

    public CacheResource(LocalCache cache) {
        this.cache = cache;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        cache.stopBackgroundRefresh();
        cache.awaitInFlightOperations();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.refreshTimeSensitiveEntries();
        cache.resumeBackgroundRefresh();
    }
}
~~~

LocalCache ở đây là abstraction do ứng dụng định nghĩa. Ví dụ minh họa rằng callback có thể dừng tác vụ nền và làm mới dữ liệu phụ thuộc thời gian. Trong ứng dụng thật, cần xử lý timeout, lỗi callback, concurrency và trường hợp checkpoint bị hủy sau khi tài nguyên đã được chuẩn bị.

### CRaC không tự quyết định cách xử lý mọi tài nguyên

Runtime không hiểu đầy đủ ý nghĩa nghiệp vụ của mọi object trong heap. Một Connection có thể còn tồn tại trong memory nhưng session database phía server đã timeout. Một token có thể còn trong String nhưng đã hết hạn. Một file descriptor có thể được engine hỗ trợ ở tầng native nhưng file hoặc mount đã thay đổi.

Resource giúp ứng dụng phối hợp các hành động có ý nghĩa:

- Dừng nhận request và drain công việc đang chạy.
- Hoàn tất hoặc rollback transaction theo chính sách.
- Flush và đóng file/channel.
- Đóng hoặc tạm dừng connection pool, HTTP client và broker client.
- Lưu offset hoặc trạng thái logic cần để tiếp tục.
- Sau restore, xác thực lại dependency và tạo tài nguyên mới.

CRaC không thay thế transaction management, distributed coordination hoặc API phục hồi của dịch vụ bên ngoài.

## 3. AWS Lambda SnapStart là gì?

AWS Lambda SnapStart là tính năng managed snapshot cho các Lambda function version và runtime được dịch vụ hỗ trợ. Trong quá trình publish version, Lambda khởi tạo execution environment, thực hiện phần Init của function và tạo snapshot từ trạng thái đã chuẩn bị. Khi cần execution environment mới, Lambda có thể phục hồi từ snapshot thay vì thực hiện lại toàn bộ quá trình khởi tạo ban đầu.

Một vòng đời khái quát:

~~~text
Deploy code và cấu hình function
              |
              v
Publish một Lambda version
              |
              v
Lambda tạo execution environment
              |
              v
Chạy Init phase
              |
              v
Tạo snapshot do Lambda quản lý
              |
              v
Invocation cần execution environment
              |
              v
Lambda restore snapshot
              |
              v
Chạy restore hooks / hoàn tất phục hồi
              |
              v
Invoke handler
~~~

Các bước chi tiết, runtime được hỗ trợ, khu vực triển khai, giới hạn và hành vi cache snapshot phụ thuộc tài liệu Lambda hiện hành. Cần kiểm tra compatibility matrix của AWS cho runtime và region cụ thể trước khi thiết kế release.

### Published version là ranh giới quan trọng

SnapStart gắn với một version đã publish của Lambda function. Việc thay đổi code hoặc cấu hình rồi publish version mới tạo một phiên bản bất biến mới cho release đó; snapshot được tạo và quản lý theo vòng đời của version. Không nên hiểu SnapStart là một snapshot tùy ý mà ứng dụng có thể tạo ở bất kỳ thời điểm nào trong runtime hoặc chuyển giữa các dịch vụ.

Lambda quản lý việc tạo và phục hồi snapshot trong nền tảng. Đội ứng dụng cấu hình tính năng cho function version và chuẩn bị code để trạng thái sau restore vẫn đúng.

### SnapStart không có nghĩa function không còn cold start

SnapStart có thể giảm phần chi phí khởi tạo lặp lại, nhưng thời gian restore, restore hook, kết nối dependency, nạp credential và xử lý request đầu tiên vẫn có chi phí. Latency thực tế còn phụ thuộc kích thước trạng thái, runtime, vùng triển khai, dependency và tải hệ thống.

Đừng chỉ đo thời gian từ lúc handler bắt đầu chạy. Cần đo cả thời gian tới invocation, restore hook, kết nối dependency và p95/p99 của request đầu tiên.

## 4. So sánh CRaC và Lambda SnapStart

| Tiêu chí | API CRaC với runtime phù hợp | AWS Lambda SnapStart |
|---|---|---|
| Bản chất | API/lifecycle contract và runtime integration cho checkpoint/restore | Tính năng snapshot managed của AWS Lambda |
| Nơi chạy | Môi trường Java và nền tảng được runtime/engine hỗ trợ | AWS Lambda với runtime và region được hỗ trợ |
| Ai tạo snapshot | Quy trình vận hành/runtime/engine do đội triển khai điều phối | Lambda tạo snapshot trong lifecycle publish version |
| Ai lưu và phục hồi | Đội triển khai hoặc nền tảng tích hợp quản lý artifact và restore | AWS Lambda quản lý snapshot và execution environment |
| Mức kiểm soát | Có thể kiểm soát runtime, engine, filesystem, host và quy trình phát hành theo nền tảng | Ít quyền kiểm soát hạ tầng snapshot; tập trung vào function và cấu hình Lambda |
| Portability | Source có thể dùng CRaC API, nhưng checkpoint binary phụ thuộc runtime/engine/platform | Snapshot gắn với Lambda version và dịch vụ; không phải artifact portable |
| Lifecycle hook | Resource beforeCheckpoint và afterRestore theo runtime | Lambda cung cấp lifecycle snapshot/restore; Java có thể dùng hook CRaC tương thích theo runtime |
| Scaling | Phụ thuộc orchestrator và cách phân phối checkpoint | Lambda quản lý execution environment theo mô hình serverless |
| Networking | Đội triển khai quyết định cách đóng/mở lại connection | Phải xử lý kết nối có thể cũ theo Lambda restore lifecycle |
| Observability | Runtime, engine, host và ứng dụng cung cấp log/metric | Kết hợp Lambda logs/metrics/tracing với log của ứng dụng |
| Vận hành | Cần quản lý checkpoint artifact, compatibility và rollout | Giảm công việc quản lý engine và snapshot storage |
| Phù hợp | Service Java cần kiểm soát sâu runtime hoặc chạy ngoài Lambda | Function phù hợp với mô hình event-driven/serverless của Lambda |

Điểm quan trọng là CRaC API và SnapStart không phải hai sản phẩm cùng loại. Có thể dùng cùng một số ý tưởng lifecycle và API Resource trong cả hai môi trường, nhưng cách tạo, lưu, phân phối và restore snapshot là khác nhau.

## 5. Khác biệt về quyền kiểm soát và trách nhiệm vận hành

### Khi chọn CRaC

Đội vận hành thường phải chịu trách nhiệm nhiều hơn cho:

- Chọn JDK vendor/build và CRaC runtime.
- Chọn checkpoint engine và nền tảng được hỗ trợ.
- Chuẩn bị filesystem, kernel, CPU và container.
- Quyết định thời điểm tạo checkpoint.
- Lưu trữ, checksum, ký và phân phối checkpoint artifact.
- Kiểm tra tương thích producer/consumer.
- Điều phối drain traffic, checkpoint, restore và readiness.
- Tạo cold-start fallback khi checkpoint không sử dụng được.

Đổi lại, có thể tích hợp CRaC vào service chạy trên VM, container hoặc nền tảng riêng nếu tổ hợp runtime/engine hỗ trợ. Đội triển khai có thể chọn cách rollout, placement và quan sát phù hợp với hệ thống.

### Khi chọn SnapStart

Lambda quản lý nhiều phần việc nền tảng:

- Tạo snapshot theo lifecycle của published function version.
- Lưu và phân phối snapshot trong phạm vi dịch vụ.
- Phục hồi execution environment khi cần.
- Tích hợp với mô hình invoke và scaling của Lambda.

Đội ứng dụng vẫn cần:

- Chọn runtime/region được hỗ trợ.
- Thiết kế Init phase hợp lý.
- Xử lý state cần duy nhất theo execution environment.
- Làm mới token, connection và dữ liệu phụ thuộc thời gian sau restore.
- Đảm bảo restore hook hoàn tất trước khi dùng tài nguyên.
- Đo cold start và request latency thực tế.

Managed service giảm phần việc quản lý engine, nhưng cũng giới hạn quyền kiểm soát chi tiết đối với host, kernel, checkpoint file và lịch restore. Nếu cần can thiệp ở tầng đó, Lambda có thể không phải mô hình phù hợp.

## 6. Vòng đời tài nguyên: điểm giao nhau giữa hai lựa chọn

Dù dùng CRaC trực tiếp hay SnapStart, một quy tắc vẫn giống nhau: object nằm trong heap không đồng nghĩa tài nguyên bên ngoài còn hợp lệ.

Ví dụ:

- JDBC connection có thể bị database đóng trong thời gian snapshot tồn tại.
- HTTP keep-alive socket có thể hết hạn hoặc bị load balancer đóng.
- DNS result có thể thay đổi.
- Token hoặc certificate có thể hết hạn/rotation.
- Thread nền hoặc scheduler có thể tiếp tục với giả định về thời gian không còn đúng.
- SecureRandom, nonce và counter có thể bị nhân bản giữa các execution environment.

### Chuẩn bị trước snapshot

Trước snapshot, cần quyết định tài nguyên nào:

- Có thể giữ nguyên vì được runtime/service hỗ trợ và không phụ thuộc thời gian.
- Cần flush và đóng.
- Cần dừng để không có thao tác đang chạy.
- Cần loại khỏi snapshot vì chứa state riêng của instance.
- Cần làm mới sau restore.

Không nên đóng mọi tài nguyên một cách máy móc. Một cache bất biến hoặc dữ liệu tính toán tốn kém có thể được giữ lại nếu hợp lệ cho mọi instance. Một connection có thể được giữ nếu runtime và dịch vụ xác nhận cách dùng đó an toàn; tuy nhiên, cần kiểm tra lại sau restore.

### Phục hồi sau snapshot

Sau restore:

1. Xác định execution environment hiện tại.
2. Tạo lại danh tính riêng nếu cần.
3. Làm mới token hoặc secret ngắn hạn.
4. Tạo lại connection và client đã đóng hoặc có nguy cơ stale.
5. Làm mới dữ liệu phụ thuộc thời gian.
6. Xác nhận dependency bắt buộc đã sẵn sàng.
7. Chỉ sau đó mới cho phép xử lý request.

Với Lambda, phần code khởi tạo trong Init không tự động chạy lại như cold start khi snapshot được restore. Dùng restore hook phù hợp để xử lý những việc phải thực hiện cho từng execution environment. Với CRaC trực tiếp, afterRestore là callback dành cho phần phục hồi tương ứng.

## 7. Dùng CRaC Resource trong ứng dụng Java chạy trên Lambda SnapStart

Java runtime của Lambda có thể cung cấp tích hợp hook tương thích với CRaC API cho SnapStart. Nhờ vậy, một số logic Resource có thể được dùng để chuẩn bị trước snapshot và phục hồi sau restore. Cần xác nhận runtime version, dependency và hướng dẫn AWS hiện hành trước khi áp dụng; không phải mọi runtime hoặc phiên bản đều có cùng hành vi.

Ví dụ dưới đây minh họa một client cần đóng trước snapshot và tạo lại sau restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApiClientResource implements Resource {
    private final ApiClientFactory factory;
    private volatile ApiClient client;

    public ApiClientResource(ApiClientFactory factory) {
        this.factory = factory;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    public ApiClient client() {
        ApiClient current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "API client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = factory.create();
        client.healthCheck();
    }
}
~~~

ApiClient và ApiClientFactory là kiểu minh họa do ứng dụng định nghĩa. Trong thực tế, việc tạo client có thể cần lấy credential mới, xác minh endpoint và đặt timeout. Nếu healthCheck() thất bại, không nên công bố client dở dang hoặc để handler tiếp tục dùng dependency chưa sẵn sàng.

Với Lambda SnapStart, đăng ký Resource phải diễn ra trong quá trình Init trước khi snapshot được tạo. beforeCheckpoint được dùng cho bước chuẩn bị snapshot; afterRestore chạy khi execution environment được phục hồi theo hook mà runtime hỗ trợ. Không giả định constructor hoặc mọi callback startup sẽ chạy lại trên từng invocation.

Nếu cùng một ứng dụng chạy cả ngoài Lambda và trên runtime CRaC riêng, có thể tái sử dụng logic quản lý tài nguyên nhưng vẫn cần kiểm tra integration, thứ tự callback và hành vi lỗi của từng môi trường.

## 8. Init phase và Restore phase trong Lambda

Lambda chia vòng đời execution environment thành các giai đoạn. Với SnapStart, Init phase diễn ra trước khi snapshot được tạo cho function version. Restore phase diễn ra khi Lambda khởi tạo một execution environment mới từ snapshot.

Một số nguyên tắc:

- Đưa công việc dùng chung, ổn định và tốn thời gian vào Init nếu nó an toàn để snapshot.
- Không tạo token hoặc identity duy nhất cho một execution environment trong Init nếu các giá trị đó sẽ bị sao chép sang nhiều bản restore.
- Đưa công việc cần riêng theo execution environment vào restore hook.
- Đảm bảo kết nối được tạo lại hoặc xác minh trước khi handler phụ thuộc vào chúng.
- Không phụ thuộc vào thời gian đã trôi qua trong snapshot; dùng clock hiện tại sau restore cho TTL, expiry và deadline.

### Ví dụ phân loại công việc

| Công việc | Init trước snapshot | Restore hook / sau restore |
|---|---|---|
| Parse schema bất biến | Phù hợp | Không cần lặp lại nếu không thay đổi |
| Tạo object mapper và serializer | Phù hợp nếu an toàn | Kiểm tra nếu phụ thuộc cấu hình runtime |
| Nạp dữ liệu tham chiếu công khai, ổn định | Có thể | Refresh nếu dữ liệu có TTL/version |
| Lấy access token ngắn hạn | Tránh lưu token dùng chung trong snapshot | Lấy token phù hợp với execution environment |
| Mở JDBC/HTTP connection | Chỉ khi có hỗ trợ và được xác minh an toàn | Thường cần reconnect/validate theo client lifecycle |
| Tạo nonce/counter riêng cho instance | Không tạo một trạng thái dùng chung rồi clone | Khởi tạo hoặc xin range mới |
| Tạo private key riêng của replica | Không đưa private key riêng vào snapshot dùng chung | Lấy key/handle riêng theo identity |
| Nạp class và tạo object thuần | Phù hợp | Không cần chạy lại trừ khi có yêu cầu |

Không phải mọi công việc trong bảng đều bắt buộc ở restore hook. Quyết định cuối cùng phụ thuộc loại dữ liệu, vòng đời dependency và semantics của runtime.

## 9. Bảo mật khi nhân bản trạng thái

Snapshot có thể chứa heap, static field, cache, token, private key, session và dữ liệu nhạy cảm khác. Khi một snapshot được phục hồi thành nhiều execution environment, những giá trị đó có thể xuất hiện ở nhiều bản sao.

### Token và credential

Không nên để nhiều replica dùng cùng refresh token có rotation hoặc token được cấp riêng cho một instance. Dùng workload identity hoặc cơ chế cấp credential sau restore để mỗi instance nhận token phù hợp.

### Randomness và nonce

Không giả định một SecureRandom đã tạo trước snapshot sẽ tự có trạng thái độc lập trong mọi bản restore. Với nonce cần uniqueness dưới cùng key, dùng key riêng, range allocator bền vững hoặc cơ chế được thiết kế để không lặp. Reseed phải dùng nguồn entropy được provider và nền tảng hỗ trợ; timestamp hoặc PID không phải entropy mật mã.

### Private key và certificate

Public trust material có thể được chia sẻ có chủ đích. Private key định danh riêng nên được tạo hoặc lấy từ KMS/HSM sau restore. Nếu nhiều execution environment dùng chung một identity, cần chấp nhận rõ hệ quả về audit, revocation và phạm vi ảnh hưởng.

### Bảo vệ snapshot

Với CRaC tự quản lý, đội vận hành phải bảo vệ checkpoint artifact, quyền đọc/ghi, checksum, chữ ký và quy trình phân phối. Với SnapStart, AWS quản lý snapshot storage và lifecycle nền tảng, nhưng ứng dụng vẫn phải xử lý secret trong heap và tuân theo quyền IAM, chính sách mã hóa và bảo mật của Lambda.

Managed snapshot không làm cho dữ liệu trong snapshot tự động an toàn về mặt nghiệp vụ. Hãy hạn chế secret tồn tại trong heap, không log token/private key và cấp lại state riêng sau restore.

## 10. Khả năng tương thích và portability

CRaC API giúp tách một phần logic vòng đời tài nguyên khỏi cách tạo checkpoint. Nhưng checkpoint binary vẫn phụ thuộc runtime, engine, OS, kernel, CPU, native library và cấu hình. Một checkpoint tạo trên JDK/runtime này không mặc định có thể restore trên runtime khác.

Lambda SnapStart có ranh giới tương thích riêng:

- Snapshot thuộc Lambda function version và runtime mà dịch vụ quản lý.
- Function phải dùng runtime/region và cấu hình SnapStart được AWS hỗ trợ.
- Không thể lấy snapshot nội bộ của Lambda rồi dùng như checkpoint CRaC độc lập trên VM hoặc Kubernetes.
- Không thể lấy checkpoint CRaC tùy ý rồi yêu cầu Lambda restore nó.
- Thay đổi code/runtime và publish version mới tạo lifecycle snapshot mới theo cơ chế của dịch vụ.

Nếu muốn chạy cùng code ở nhiều môi trường, hãy tái sử dụng domain logic và abstraction quản lý tài nguyên, không kỳ vọng tái sử dụng cùng binary checkpoint. Giữ phần tích hợp nền tảng ở module hoặc adapter riêng.

## 11. Hiệu năng và chi phí

### Những yếu tố quyết định lợi ích

Snapshot có ích nhất khi phần khởi tạo có thể được thực hiện một lần và trạng thái đó an toàn để dùng lại:

- Nạp class và tạo framework context.
- Parse schema, template hoặc metadata bất biến.
- Khởi tạo serializer, mapper và cấu trúc dữ liệu.
- Tính toán dữ liệu tham chiếu không chứa state riêng của instance.
- Làm nóng một số đường code nếu runtime và nền tảng giữ được lợi ích đó.

Snapshot ít hữu ích hơn nếu phần lớn thời gian startup nằm ở những dependency phải tạo lại sau restore, hoặc nếu mỗi instance cần làm nhiều công việc riêng trước khi sẵn sàng.

### So sánh chi phí vận hành

| Yếu tố | CRaC tự quản lý | Lambda SnapStart |
|---|---|---|
| Hạ tầng chạy ứng dụng | VM/container/host do đội chọn và vận hành | Hạ tầng Lambda managed |
| Snapshot artifact | Đội xây quy trình tạo, lưu, ký, phân phối và xóa | Lambda quản lý snapshot lifecycle |
| Tối ưu runtime | Có thể kiểm soát sâu hơn nếu nền tảng cho phép | Bị giới hạn bởi runtime và cấu hình Lambda |
| Điều phối restore | Orchestrator hoặc nền tảng do đội cấu hình | Lambda tự điều phối execution environment |
| Theo dõi tương thích | Cần ma trận producer/consumer | Theo runtime/region/service support của AWS |
| Công sức vận hành | Cao hơn ở tầng checkpoint và host | Thấp hơn ở tầng snapshot infrastructure |
| Chi phí | Compute, storage, network và vận hành theo kiến trúc riêng | Chi phí Lambda và các dịch vụ liên quan theo pricing hiện hành |

Không nên so sánh chỉ bằng một con số cold-start. Tính cả chi phí build snapshot, storage, memory, idle capacity, invocation, dependency và công sức vận hành. Cấu trúc giá của AWS có thể thay đổi; dùng trang pricing hiện hành để tính cho workload thực tế thay vì dựa vào một mức giá cố định trong tài liệu kỹ thuật.

## 12. Khi nào nên chọn CRaC?

CRaC thường phù hợp khi:

- Ứng dụng là Java service chạy trên VM, container hoặc nền tảng riêng.
- Đội cần kiểm soát runtime, checkpoint engine và placement.
- Có quy trình phát hành artifact và kiểm tra tương thích rõ ràng.
- Có thể thiết kế lifecycle cho database, broker, HTTP client, file và native resource.
- Cần tối ưu startup của một service tồn tại lâu dài hoặc nhiều instance.
- Nền tảng triển khai có JDK/CRaC runtime và engine được hỗ trợ.

CRaC có thể phù hợp với Kubernetes hoặc môi trường container hóa, nhưng cần xác minh kernel, container runtime, quyền, storage, namespace và cách orchestration checkpoint/restore. Không phải cứ chạy Java trong container là có thể dùng checkpoint.

## 13. Khi nào nên chọn Lambda SnapStart?

SnapStart thường phù hợp khi:

- Workload đã phù hợp với mô hình event-driven của AWS Lambda.
- Runtime Java và region mục tiêu nằm trong danh sách được hỗ trợ.
- Cold start là yếu tố đáng kể đối với latency.
- Phần Init có thể được chuẩn bị trước snapshot và không chứa state riêng cần tạo lại.
- Đội muốn AWS quản lý snapshot infrastructure và execution environment.
- Handler và dependency có thể phục hồi đúng trong lifecycle Lambda.

SnapStart không thay thế mọi lựa chọn compute. Nếu workload cần process liên tục, daemon nền dài hạn, quyền kiểm soát host hoặc giao thức kết nối kéo dài theo cách Lambda không phù hợp, hãy đánh giá container/VM hoặc nền tảng khác.

## 14. Khi nào không nên dùng snapshot?

Snapshot có thể không đem lại lợi ích hoặc tạo thêm rủi ro khi:

- Phần khởi tạo chủ yếu là kết nối dependency phải làm lại sau restore.
- Init tạo side effect nghiệp vụ như gửi message, ghi database hoặc tạo đơn hàng.
- Ứng dụng giữ token, nonce, private key hoặc identity riêng không thể chia sẻ giữa các bản sao.
- Nhiều thread/task nền không thể đưa về trạng thái an toàn.
- Native library hoặc runtime không hỗ trợ checkpoint theo nền tảng.
- Snapshot quá lớn khiến storage, transfer hoặc restore chiếm phần lớn latency.
- Tần suất thay đổi cấu hình hoặc secret làm snapshot nhanh chóng lỗi thời.
- Workload cần khả năng portability của artifact mà runtime/engine không cung cấp.

Trong các trường hợp đó, có thể tối ưu cold start bằng cách giảm công việc Init, lazy-load dependency tùy chọn, dùng connection pool phù hợp, cải thiện classpath, giảm allocation hoặc chọn compute model khác.

## 15. Lộ trình chuyển từ CRaC sang SnapStart hoặc ngược lại

Không nên bắt đầu bằng việc cố chuyển checkpoint binary. Hãy tách phần logic ứng dụng khỏi cơ chế snapshot.

### Bước 1: Tách domain logic và resource adapter

Giữ business service không phụ thuộc vào API độc quyền của một nền tảng. Tạo abstraction cho các tài nguyên cần chuẩn bị và phục hồi, ví dụ:

- Remote client manager.
- Credential provider.
- File/resource manager.
- Work admission gate.
- Security context provider.

### Bước 2: Định nghĩa hợp đồng lifecycle

Xác định rõ hành động trước snapshot và sau restore. Ví dụ, prepareForSnapshot() dừng background work và đóng client; resumeAfterRestore() lấy credential mới, tạo client và kiểm tra readiness.

Không đưa logic nghiệp vụ như tạo đơn hàng hoặc publish message vào callback snapshot.

### Bước 3: Viết adapter cho từng nền tảng

Với CRaC, adapter triển khai org.crac.Resource và đăng ký với context phù hợp.

Với Lambda SnapStart, dùng hook mà runtime Lambda hỗ trợ, bao gồm CRaC-compatible Resource nếu runtime version đó cung cấp. Không tự giả định hook có cùng thứ tự hoặc ngữ nghĩa giữa các runtime.

### Bước 4: Giữ phần phụ thuộc nền tảng ở module riêng

Một cấu trúc có thể là:

~~~text
application/
  domain/
    OrderService.java
    ResourceLifecycle.java
  infrastructure/
    RemoteClientManager.java
    CredentialProvider.java
  runtime-crac/
    CracResourceAdapter.java
  runtime-lambda/
    LambdaSnapStartIntegration.java
~~~

Không cần tạo hai module nếu chỉ triển khai một nền tảng. Cấu trúc này minh họa cách giữ phần phụ thuộc platform tách khỏi domain khi thực sự cần nhiều deployment target.

### Bước 5: Tạo pipeline riêng cho từng nền tảng

CRaC pipeline cần pin JDK/engine/platform, tạo checkpoint, ghi manifest, checksum, ký artifact và kiểm thử restore.

Lambda pipeline cần build function artifact, publish version, cấu hình SnapStart theo hướng dẫn dịch vụ và kiểm thử execution environment sau restore. Không đưa checkpoint CRaC vào package Lambda.

### Bước 6: Kiểm thử semantics, không chỉ startup time

Kiểm tra token, certificate, nonce, connection, scheduler, clock, cache, readiness và side effect. Chạy nhiều instance từ cùng snapshot để phát hiện state bị nhân bản.

## 16. Kiểm thử và đo lường trước khi chọn

Một so sánh công bằng cần cùng workload, dữ liệu và yêu cầu correctness.

### Các chỉ số nên đo

- Thời gian cold start không dùng snapshot.
- Thời gian tạo snapshot/checkpoint nếu đội sở hữu bước đó.
- Thời gian restore.
- Thời gian chạy restore hook.
- Thời gian tới readiness.
- Latency request đầu tiên.
- p50/p95/p99 latency của nhóm request đầu tiên.
- CPU và memory trong Init/restore.
- Số lần kết nối lại database, broker và API.
- Lỗi timeout, stale connection hoặc credential.
- Chi phí compute, storage và vận hành trong cùng chu kỳ tải.

### Kịch bản kiểm thử

1. Khởi động từ cold start và ghi baseline.
2. Khởi tạo snapshot theo cơ chế của từng nền tảng.
3. Restore nhiều execution environment từ cùng snapshot.
4. Xác nhận token và identity được cấp đúng theo từng instance.
5. Kiểm tra database/HTTP/broker connection còn hợp lệ hoặc được tạo lại.
6. Kiểm tra SecureRandom, nonce, counter và replay state.
7. Thay đổi secret/configuration trong khoảng thời gian snapshot tồn tại.
8. Làm dependency không sẵn sàng và xác nhận readiness chưa mở.
9. Kiểm tra request đầu tiên và p99 sau restore.
10. Thực hiện rollout version mới và rollback theo quy trình đã kiểm thử.

Với Lambda, đo trên published function version có SnapStart được bật và kiểm tra restore behavior trong môi trường AWS mục tiêu. Với CRaC, đo trên đúng JDK, engine, kernel, container và storage sẽ dùng trong production. Kết quả từ máy phát triển không thay thế được kiểm thử trên môi trường triển khai.

## 17. Những hiểu nhầm thường gặp

**“CRaC và SnapStart là cùng một sản phẩm.”**

CRaC là API/lifecycle integration và hệ sinh thái runtime checkpoint/restore. SnapStart là tính năng snapshot managed của Lambda. Chúng có thể dùng các hook tương tự nhưng quyền sở hữu snapshot và hạ tầng khác nhau.

**“Dùng CRaC API nghĩa là checkpoint có thể chuyển sang Lambda.”**

Không. API Resource giúp quản lý vòng đời tài nguyên; checkpoint binary vẫn thuộc runtime/engine/platform đã tạo nó. Lambda quản lý snapshot theo Lambda version.

**“SnapStart chạy lại toàn bộ Init khi restore.”**

Không nên giả định như vậy. Trạng thái Init được snapshot; phần cần làm mới cho execution environment phải nằm trong restore hook hoặc cơ chế lifecycle tương ứng.

**“Snapshot giữ kết nối database nên không cần reconnect.”**

Kết nối có thể stale hoặc server đã đóng session. Phải xác minh client/connection theo hướng dẫn driver và runtime.

**“Mọi token và SecureRandom có thể dùng chung sau restore.”**

Không. Snapshot có thể nhân bản trạng thái. Credential, identity, nonce và random state cần được xử lý theo yêu cầu riêng của từng instance.

**“SnapStart loại bỏ hoàn toàn cold start.”**

Snapshot giảm một phần công việc khởi tạo, nhưng restore, hook, dependency và request đầu tiên vẫn có chi phí.

**“CRaC luôn cho nhiều quyền kiểm soát hơn mà không tăng vận hành.”**

CRaC cho phép kiểm soát sâu hơn trên nền tảng phù hợp, nhưng đội phải quản lý runtime, engine, artifact, compatibility và rollout.

**“Managed snapshot không cần kiểm thử lifecycle.”**

AWS quản lý snapshot infrastructure, nhưng ứng dụng vẫn chịu trách nhiệm về correctness của state, credential, connection và side effect sau restore.

## 18. Quy trình ra quyết định

Có thể dùng các câu hỏi sau để chọn hướng:

1. Ứng dụng có bắt buộc chạy trên AWS Lambda không? Nếu có, đánh giá SnapStart trong danh sách runtime/region được hỗ trợ.
2. Có cần kiểm soát checkpoint engine, host, filesystem và restore orchestration không? Nếu có, đánh giá CRaC trên runtime/platform hỗ trợ.
3. Có thể đưa phần khởi tạo tốn thời gian vào snapshot mà không lưu side effect hoặc identity riêng không?
4. Các dependency có thể được đóng/mở hoặc xác minh lại trong lifecycle hook không?
5. Có thể cấp lại token, certificate, nonce range và identity cho từng instance không?
6. Snapshot size và storage I/O có phù hợp với latency mục tiêu không?
7. Đội có khả năng vận hành compatibility matrix và release artifact nếu tự quản lý CRaC không?
8. Có cold-start fallback và quy trình rollback được kiểm thử không?

Nếu workload phù hợp Lambda và mục tiêu chính là giảm thời gian Init, SnapStart thường là hướng đơn giản hơn về vận hành. Nếu cần checkpoint cho Java service ngoài Lambda hoặc cần quyền kiểm soát sâu hơn đối với runtime/host, CRaC có thể phù hợp hơn. Cần đo và kiểm chứng trên đúng môi trường trước khi quyết định.

## 19. Kết luận

CRaC API và AWS Lambda SnapStart cùng giúp giảm chi phí khởi tạo lặp lại bằng cách chuẩn bị trạng thái trước rồi phục hồi trạng thái đó. CRaC cung cấp hợp đồng Resource và được tích hợp với JDK/runtime cùng checkpoint engine mà đội triển khai lựa chọn. SnapStart là tính năng managed của Lambda, gắn với published function version và để AWS quản lý snapshot lifecycle.

Có thể tái sử dụng tư duy lifecycle và một phần Resource code giữa hai môi trường, nhưng không nên kỳ vọng checkpoint binary portable hoặc giả định mọi callback có ngữ nghĩa giống nhau. Hãy phân loại state có thể chia sẻ, làm mới credential và connection theo từng execution environment, bảo đảm nonce/identity không bị nhân bản sai, đo restore cùng request latency và chọn nền tảng theo yêu cầu kiểm soát, vận hành và mô hình triển khai.
