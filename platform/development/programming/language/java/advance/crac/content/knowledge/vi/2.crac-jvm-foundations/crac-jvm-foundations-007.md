# Ranh giới giữa trạng thái Java, mã native và trạng thái hệ điều hành

Khi một ứng dụng Java chạy, trạng thái của nó không nằm hoàn toàn trong các object trên Java heap. Một phần trạng thái do JVM quản lý, một phần nằm trong bộ nhớ native hoặc thư viện được nạp vào tiến trình, và một phần khác do hệ điều hành quản lý bên ngoài không gian địa chỉ của tiến trình. Ứng dụng còn có thể phụ thuộc vào trạng thái ở các hệ thống từ xa như database, message broker hoặc dịch vụ mạng.

Sự phân chia này đặc biệt quan trọng khi dùng **CRaC (Coordinated Restore at Checkpoint)**. Checkpoint lưu trạng thái tiến trình để có thể tiếp tục chạy từ trạng thái đã chuẩn bị. Tuy nhiên, việc một object Java vẫn còn trong heap sau restore không có nghĩa mọi tài nguyên mà object đó đại diện vẫn hoạt động. Một wrapper Java có thể còn nguyên nhưng socket, file descriptor, native handle hoặc phiên kết nối ở hệ thống bên ngoài có thể đã thay đổi, hết hạn hoặc không thể khôi phục trong môi trường mới.

Để thiết kế ứng dụng tương thích với CRaC, cần nhận diện trạng thái thuộc lớp nào, ai sở hữu nó và cách kiểm tra hoặc tạo lại trạng thái đó sau restore.

## 1. Ba lớp trạng thái trong một tiến trình Java

Có thể chia trạng thái mà ứng dụng sử dụng thành ba lớp lớn:

1. **Trạng thái Java và JVM:** object, class, thread Java, stack, heap, dữ liệu runtime và các cấu trúc mà JVM quản lý.
2. **Trạng thái native trong tiến trình:** vùng nhớ native, thư viện C/C++, JNI, JNA, Foreign Function & Memory API, native thread và các handle do thư viện quản lý.
3. **Trạng thái hệ điều hành:** file descriptor, socket, pipe, timer, khóa hệ thống, namespace, quyền, mount, thiết bị và các kernel object.

Ngoài ba lớp trên còn có trạng thái ở hệ thống bên ngoài tiến trình. Ví dụ, transaction trong database, consumer offset của message broker, phiên đăng nhập hoặc dữ liệu trong cache từ xa không nằm trong bộ nhớ tiến trình Java.

Sơ đồ sau minh họa mối quan hệ giữa các lớp:

~~~mermaid
flowchart TB
    subgraph P["Tiến trình Java"]
        subgraph J["JVM và Java"]
            H["Java heap: object, collection, cache"]
            T["Java thread, stack, class metadata"]
            R["JVM runtime, JIT, class loader"]
        end
        subgraph N["Native trong tiến trình"]
            M["Native memory, direct buffer"]
            L["JNI / JNA / FFM"]
            S["Thư viện C/C++, native thread, native global state"]
        end
        H --> L
        T --> L
        L --> M
        L --> S
    end
    subgraph O["Hệ điều hành / kernel"]
        F["File descriptor, socket, pipe"]
        K["Kernel object, timer, lock"]
        E["Namespace, cgroup, quyền, mount"]
    end
    subgraph X["Hệ thống bên ngoài"]
        D["Database / message broker"]
        Q["Dịch vụ mạng / cache / identity provider"]
    end
    L --> F
    S --> K
    F --> D
    F --> Q
~~~

Một thành phần có thể đi qua nhiều lớp. Chẳng hạn, ứng dụng giữ một object Socket trên heap Java. Object đó liên kết với một socket do hệ điều hành quản lý. Socket lại đại diện cho một kết nối đến máy chủ từ xa. Object Java, socket kernel và trạng thái phiên ở máy chủ là ba phần riêng biệt.

## 2. Trạng thái Java và JVM

### 2.1. Java heap

Java heap chứa các object được tạo bởi ứng dụng và thư viện: entity, collection, cache, cấu hình đã đọc, object quản lý kết nối và các wrapper cho tài nguyên khác.

Ví dụ:

~~~java
public final class ApplicationState {
    private final Map<String, String> configuration;
    private final List<String> cachedValues;
    private final UserSession currentSession;

    public ApplicationState(
            Map<String, String> configuration,
            List<String> cachedValues,
            UserSession currentSession) {
        this.configuration = configuration;
        this.cachedValues = cachedValues;
        this.currentSession = currentSession;
    }
}
~~~

Các object như trên nằm trong vùng nhớ của tiến trình. Khi checkpoint và restore được JDK hỗ trợ thực hiện đúng, trạng thái heap là một phần quan trọng của trạng thái được khôi phục. Object graph, giá trị field và quan hệ tham chiếu có thể tiếp tục tồn tại mà ứng dụng không phải tạo lại từng object.

Tuy nhiên, heap chỉ lưu trạng thái mà object biểu diễn. Nếu currentSession chứa một token đã hết hạn hoặc configuration là bản cấu hình cũ, restore không tự làm mới các giá trị đó. Dữ liệu vẫn có thể đúng về mặt bộ nhớ nhưng không còn đúng về mặt nghiệp vụ.

### 2.2. Class, class loader và dữ liệu runtime

JVM quản lý nhiều cấu trúc ngoài Java heap, chẳng hạn class metadata, class loader, constant pool, thông tin phương thức và mã đã biên dịch bởi JIT. Một số vùng như Metaspace và code cache nằm trong không gian bộ nhớ của tiến trình nhưng không phải object Java thông thường.

Với CRaC, JDK và cơ chế checkpoint cần phối hợp để trạng thái JVM có thể được lưu và khôi phục nhất quán. Không nên đồng nhất checkpoint CRaC với việc chỉ ghi Java heap ra đĩa: trạng thái runtime của JVM cũng tham gia vào quá trình.

Class loader và thư viện đã được nạp cũng có thể giữ trạng thái. Ví dụ, ứng dụng có thể đã nạp một thư viện native bằng System.loadLibrary(). Sau restore, trạng thái tiến trình có thể vẫn phản ánh thư viện đã được nạp. Việc thư viện có hoạt động an toàn hay không còn phụ thuộc vào dữ liệu native, tài nguyên hệ điều hành và các giả định của chính thư viện.

### 2.3. Thread Java và stack

Mỗi Java thread đang chạy có trạng thái thực thi như program counter, stack frame, biến cục bộ và trạng thái đồng bộ. JVM phối hợp với hệ điều hành để thực thi các thread này.

Một thread có thể đang:

- Chạy bytecode Java.
- Thực hiện lời gọi JNI vào mã native.
- Chờ monitor hoặc lock.
- Chờ I/O.
- Ngủ hoặc chờ một tác vụ theo lịch.
- Thực hiện công việc trong executor hoặc scheduler.

Trạng thái thread là một phần nhạy cảm của checkpoint. Nếu ứng dụng checkpoint khi một thread đang giữ lock, đang ghi dữ liệu hoặc đang ở giữa một thao tác native phụ thuộc hệ thống bên ngoài, restore có thể tiếp tục với trạng thái không phù hợp với môi trường hiện tại.

Ứng dụng cần đưa các thread liên quan về trạng thái an toàn trước checkpoint. Điều này thường có nghĩa là ngừng nhận công việc mới, chờ tác vụ đang chạy hoàn tất hoặc yêu cầu thread dừng tại một điểm có thể phục hồi.

### 2.4. Giá trị Java có thể cũ dù bộ nhớ được khôi phục

Một số giá trị vẫn hợp lệ về cấu trúc nhưng không còn hợp lệ theo thời gian:

- Token xác thực đã hết hạn.
- Cache entry đã vượt quá TTL.
- Thời điểm hết hạn của session đã qua.
- DNS hoặc địa chỉ dịch vụ đã thay đổi.
- Cấu hình theo instance không còn khớp với môi trường restore.
- Lịch chạy đã bỏ lỡ thời điểm thực thi trong lúc tiến trình không hoạt động.

Ví dụ, object sau vẫn có thể được khôi phục nguyên vẹn:

~~~java
public final class CachedCredential {
    private final String token;
    private final Instant expiresAt;

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Ứng dụng cần kiểm tra expiresAt sau restore và làm mới token nếu cần. Việc object còn nguyên trong heap không thay thế cho việc xác nhận hiệu lực của credential với identity provider.

## 3. Native state: bộ nhớ và thư viện nằm trong tiến trình

Java có thể gọi mã native thông qua JNI, JNA hoặc Foreign Function & Memory API. Các thư viện native thường được viết bằng C/C++, nhưng cũng có thể là thư viện hệ thống hoặc thư viện của nhà cung cấp.

### 3.1. Native memory

Native memory là bộ nhớ được cấp phát ngoài Java heap, ví dụ bằng malloc, mmap, API của thư viện hoặc cơ chế cấp phát native của JVM. Một số API Java tạo vùng nhớ native nhưng cung cấp wrapper Java để truy cập.

Ví dụ, ByteBuffer.allocateDirect() tạo direct buffer có dữ liệu nằm ngoài heap thông thường:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
buffer.putInt(42);
buffer.flip();
~~~

Direct buffer vẫn có thể được tham chiếu từ heap Java, trong khi vùng dữ liệu thực tế nằm ở native memory. Với checkpoint cấp tiến trình, vùng nhớ native được ánh xạ trong không gian địa chỉ tiến trình có thể thuộc phạm vi trạng thái bộ nhớ được lưu. Nhưng điều đó không có nghĩa mọi tài nguyên được cấp phát native đều an toàn sau restore.

Cần phân biệt:

- **Vùng nhớ native:** các byte được cấp phát trong không gian địa chỉ của tiến trình.
- **Tài nguyên mà vùng nhớ đại diện:** file descriptor, socket, thiết bị, vùng shared memory hoặc handle do kernel quản lý.
- **Trạng thái ở tiến trình khác:** dịch vụ hoặc server mà thư viện native đang giao tiếp.

Một buffer chứa cấu trúc dữ liệu có thể được khôi phục, trong khi file descriptor được lưu trong một field của cấu trúc đó lại cần được kiểm tra hoặc mở lại.

### 3.2. Trạng thái nội bộ của thư viện native

Thư viện native có thể duy trì:

- Biến global và static.
- Bảng tra cứu hoặc cache nội bộ.
- Con trỏ đến vùng nhớ được cấp phát động.
- Native thread và thread-local storage.
- Mutex, condition variable và trạng thái đồng bộ.
- Bộ đệm I/O.
- File descriptor và socket.
- Handle đến thiết bị hoặc tài nguyên do thư viện khác quản lý.

Các biến global và vùng nhớ nội bộ thuộc không gian địa chỉ tiến trình. Chúng có thể nằm trong trạng thái bộ nhớ được checkpoint. Nhưng thư viện có thể giữ những giả định về kernel hoặc dịch vụ từ xa. Nếu những giả định đó không còn đúng sau restore, việc tiếp tục gọi hàm native có thể gây lỗi.

Ví dụ, thư viện có thể giữ một biến static int connection_fd chứa số file descriptor. Giá trị số nguyên vẫn còn trong bộ nhớ sau restore, nhưng descriptor tương ứng phải thực sự hợp lệ trong tiến trình đã khôi phục. Không thể kết luận chỉ từ việc biến vẫn giữ nguyên giá trị.

### 3.3. JNI, JNA và Foreign Function & Memory API

Ba cách phổ biến để kết nối Java với mã native có những đặc điểm khác nhau:

| Cơ chế | Vai trò | Điểm cần chú ý khi checkpoint |
|---|---|---|
| JNI | Java gọi hàm native và native gọi ngược vào JVM | Global reference, native global state, thread attach/detach, con trỏ và handle |
| JNA | Gọi hàm native qua lớp ánh xạ tự động | Đối tượng proxy Java có thể còn tồn tại trong khi handle hoặc tài nguyên native đã cũ |
| Foreign Function & Memory API | Gọi hàm native và quản lý vùng nhớ native bằng API Java | Lifetime của arena/segment, địa chỉ native, thư viện được liên kết và tài nguyên do hàm native tạo ra |

Cả ba cơ chế đều có thể tạo ra ranh giới giữa object Java và trạng thái native. Việc checkpoint khôi phục được bộ nhớ không thay thế cho hợp đồng vòng đời của thư viện.

### 3.4. Native thread

Một thư viện C/C++ có thể tự tạo thread bằng pthread hoặc cơ chế tương đương mà không thông qua Thread của Java. Các thread này vẫn thuộc tiến trình hệ điều hành, nhưng JVM không nhất thiết quản lý vòng đời của chúng như Java thread.

Ứng dụng cần biết thư viện có tạo native thread hay không. Trước checkpoint, hãy dùng API của thư viện để:

1. Ngừng nhận công việc mới.
2. Yêu cầu worker hoàn tất hoặc dừng tại điểm an toàn.
3. Đợi worker xác nhận đã dừng hoặc đã ở trạng thái có thể checkpoint.
4. Giải phóng hoặc chuẩn bị lại các tài nguyên mà worker sử dụng.

Nếu native thread đang giữ mutex, chờ I/O hoặc thực hiện thao tác với thiết bị, cần hiểu rõ hành vi restore của thư viện và nền tảng. Không nên tự ý kết thúc thread hoặc đóng handle từ phía Java khi thư viện vẫn đang sử dụng chúng.

## 4. Trạng thái hệ điều hành

Hệ điều hành quản lý nhiều đối tượng nằm ngoài Java heap và native memory của tiến trình. Một số đối tượng có thể được cơ chế checkpoint/restore hỗ trợ, một số khác có điều kiện đặc biệt, và một số không thể khôi phục theo cách ứng dụng mong đợi.

### 4.1. File descriptor

Trên Unix/Linux, file descriptor là một số nguyên mà tiến trình dùng để tham chiếu đến tài nguyên kernel như file, socket, pipe hoặc thiết bị.

Ví dụ, Java có thể giữ một FileInputStream. Object Java lưu thông tin cần thiết để gọi xuống lớp I/O; file descriptor thực tế do hệ điều hành quản lý.

Khi checkpoint, cần xem xét cả hai phía:

- Object Java hoặc wrapper vẫn đang tham chiếu đến descriptor.
- Descriptor và tài nguyên kernel mà nó đại diện có được cơ chế checkpoint/restore khôi phục hay không.

Không nên tự đặt lại một field descriptor bằng số cũ hoặc gọi close() trực tiếp từ Java nếu thư viện sở hữu descriptor và có cơ chế cleanup riêng. Việc đóng tài nguyên cần đi qua đúng API của thành phần sở hữu nó để cập nhật cả trạng thái Java, native và hệ điều hành.

### 4.2. Socket và kết nối TCP

Socket là một tài nguyên kernel. Kết nối TCP còn liên quan đến trạng thái ở hai đầu kết nối và hạ tầng mạng. Có thể có tình huống tiến trình được restore nhưng máy chủ từ xa đã đóng phiên, load balancer đã hết thời gian chờ hoặc địa chỉ mạng không còn phù hợp.

CRIU và các nền tảng checkpoint/restore có thể hỗ trợ một số loại socket trong những điều kiện nhất định. Khả năng đó phụ thuộc vào loại socket, cấu hình mạng, kernel, quyền và trạng thái peer. Vì vậy, ứng dụng nên có quy trình làm mới kết nối đến database, HTTP service và message broker.

Đối với socket do thư viện native quản lý, hãy dùng API đóng và mở lại của thư viện. Đóng descriptor trực tiếp trong Java có thể khiến thư viện vẫn nghĩ rằng kết nối đang hoạt động.

### 4.3. Pipe, eventfd, epoll và timer

Ứng dụng native hoặc thư viện runtime có thể sử dụng các kernel object như:

- Pipe hoặc Unix domain socket để truyền dữ liệu giữa tiến trình.
- eventfd để báo hiệu giữa thread hoặc thành phần.
- epoll để theo dõi nhiều file descriptor.
- timerfd để nhận sự kiện theo thời gian.
- Signal handler và signal mask.
- File lock hoặc các cơ chế đồng bộ liên tiến trình.

Một thư viện có thể lưu số descriptor và trạng thái đăng ký sự kiện trong native memory. Nếu các kernel object được khôi phục khác với giả định của thư viện, vòng lặp sự kiện có thể ngừng hoạt động hoặc chờ vô hạn.

Cần kiểm tra tài liệu của thư viện và nền tảng. Nếu không có cam kết tương thích, hãy dừng event loop trước checkpoint và khởi tạo lại sau restore.

### 4.4. Shared memory và IPC

Shared memory cho phép nhiều tiến trình cùng truy cập một vùng dữ liệu. Trạng thái của vùng nhớ có thể phụ thuộc vào tiến trình khác, quyền truy cập, namespace và cơ chế IPC của hệ điều hành.

Checkpoint một tiến trình không đồng nghĩa với việc checkpoint đồng bộ tất cả tiến trình đang chia sẻ vùng nhớ với nó. Nếu một tiến trình khác tiếp tục thay đổi dữ liệu trong khi tiến trình Java tạm dừng, trạng thái sau restore có thể không còn nhất quán.

Với shared memory, hãy xác định:

- Tiến trình nào sở hữu vùng nhớ.
- Ai được phép ghi trong thời gian checkpoint.
- Cơ chế lock hoặc versioning có bảo vệ dữ liệu không.
- Vùng nhớ và cơ chế đồng bộ có được nền tảng hỗ trợ khôi phục không.
- Ứng dụng có thể attach lại hoặc tạo lại vùng nhớ sau restore hay không.

### 4.5. Namespace, cgroup, mount và quyền

Tiến trình chạy trong container có thể phụ thuộc vào namespace, cgroup, mount, capability, seccomp, UID/GID và các giới hạn tài nguyên. Những yếu tố này ảnh hưởng đến quyền truy cập và khả năng sử dụng tài nguyên sau restore.

Một checkpoint được tạo trong container có cấu hình cụ thể không nhất thiết có thể restore an toàn trong container có cấu hình khác. Ví dụ, đường dẫn mount có thể thay đổi, thiết bị có thể không được gắn vào, hoặc tiến trình có thể thiếu capability cần thiết.

Cần kiểm tra cấu hình runtime của môi trường tạo checkpoint và môi trường restore theo yêu cầu của JDK CRaC, CRIU và nền tảng triển khai.

## 5. Trạng thái bên ngoài tiến trình

Có một ranh giới quan trọng hơn: trạng thái của hệ thống khác không thuộc tiến trình Java. Checkpoint tiến trình không đóng băng hoặc rollback các hệ thống này.

Ví dụ:

- Database vẫn tiếp tục xử lý transaction và timeout.
- Message broker vẫn tiếp tục nhận và phân phối message.
- Remote service vẫn thay đổi dữ liệu.
- Token provider vẫn phát hành hoặc thu hồi credential.
- Cache phân tán vẫn hết hạn entry.
- Hệ thống khác vẫn có thể cập nhật dữ liệu dùng chung.

Giả sử ứng dụng giữ một kết nối database trong heap. Trước checkpoint, object Java vẫn tồn tại. Trong thời gian ứng dụng không hoạt động, database có thể đóng connection do idle timeout. Khi restore, wrapper Java có thể vẫn tồn tại nhưng phiên làm việc ở database đã mất.

Tương tự, nếu ứng dụng gửi một request đến dịch vụ từ xa rồi checkpoint khi chưa nhận phản hồi, không thể suy ra request đó chưa được xử lý. Server có thể đã thực hiện thao tác nhưng phản hồi bị mất. Sau restore, retry có thể tạo tác động trùng lặp.

Vì vậy, cần áp dụng các nguyên tắc sau:

- Hoàn tất hoặc hủy an toàn các thao tác đang chạy trước checkpoint.
- Dùng transaction và idempotency key cho thao tác có thể retry.
- Xác nhận trạng thái nghiệp vụ từ hệ thống sở hữu dữ liệu.
- Làm mới connection, session và credential sau restore.
- Thiết kế retry có giới hạn, timeout và xử lý lỗi rõ ràng.

## 6. CRaC lưu gì và ứng dụng phải xử lý gì?

Bảng dưới đây là cách phân loại thực tế. Khả năng khôi phục cuối cùng vẫn phụ thuộc vào JDK, kernel, CRIU và cấu hình môi trường.

| Loại trạng thái | Ví dụ | Hướng xử lý |
|---|---|---|
| Java heap | Object, collection, cache trong heap | Có thể tiếp tục từ trạng thái đã lưu; kiểm tra dữ liệu có còn hiệu lực |
| JVM runtime | Class metadata, thread state, runtime data | Cần JDK CRaC phối hợp với checkpoint/restore |
| Native memory | malloc, mmap, direct buffer | Kiểm tra vùng nhớ, con trỏ và lifetime của thư viện |
| Native global state | Biến static, bảng handle, cache nội bộ | Dùng API của thư viện để chuẩn bị và phục hồi |
| Native thread | pthread worker, event loop | Dừng hoặc đưa về trạng thái an toàn theo API thư viện |
| Kernel object | File descriptor, socket, pipe, timer | Xác minh loại tài nguyên được hỗ trợ; mở lại khi cần |
| Container/runtime | Namespace, mount, cgroup, capability | Đảm bảo môi trường restore đáp ứng điều kiện tương thích |
| Hệ thống từ xa | Database, broker, cache, API | Reconnect, refresh, xác minh và xử lý retry |
| Dữ liệu nhạy cảm | Token, secret, dữ liệu người dùng trong heap | Bảo vệ checkpoint như artifact chứa dữ liệu nhạy cảm |

Có thể ghi nhớ ba câu hỏi cho mỗi tài nguyên:

1. Dữ liệu của nó nằm trong bộ nhớ tiến trình hay do kernel/hệ thống khác quản lý?
2. Thành phần nào sở hữu và có trách nhiệm đóng hoặc khởi tạo lại tài nguyên?
3. Sau restore, làm sao xác nhận tài nguyên thực sự dùng được?

Nếu không trả lời được ba câu hỏi này, tài nguyên đó cần được điều tra trước khi đưa ứng dụng vào production với CRaC.

## 7. Phối hợp Java và native resource bằng CRaC

CRaC cung cấp interface org.crac.Resource để ứng dụng phối hợp với tài nguyên trước checkpoint và sau restore. Hai callback chính là:

- beforeCheckpoint(): chuẩn bị tài nguyên trước khi trạng thái tiến trình được lưu.
- afterRestore(): kiểm tra hoặc khởi tạo lại tài nguyên sau khi tiến trình được khôi phục.

### 7.1. Ví dụ quản lý native handle

Giả sử ứng dụng dùng một thư viện native để xử lý dữ liệu. Thư viện cung cấp hai hàm giả định:

- openNativeEngine() tạo engine và trả về một handle.
- closeNativeEngine(handle) dừng worker và giải phóng tài nguyên native.

Java có thể quản lý vòng đời bằng một Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class NativeEngineResource implements Resource {

    private final String configuration;
    private volatile long nativeHandle;

    public NativeEngineResource(String configuration) {
        this.configuration = configuration;
        this.nativeHandle = openNativeEngine(configuration);

        // Đăng ký để CRaC gọi callback vòng đời.
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        long handle = nativeHandle;
        if (handle != 0) {
            // Hàm native cần dừng worker và giải phóng handle
            // theo đúng hợp đồng của thư viện.
            stopAndCloseNativeEngine(handle);
            nativeHandle = 0;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Tạo handle mới trong môi trường đã restore.
        nativeHandle = openNativeEngine(configuration);
    }

    public long getNativeHandle() {
        long handle = nativeHandle;
        if (handle == 0) {
            throw new IllegalStateException(
                    "Native engine is not available");
        }
        return handle;
    }

    private static native long openNativeEngine(String configuration);

    private static native void stopAndCloseNativeEngine(long handle);
}
~~~

Đây là ví dụ minh họa. Hai phương thức native phải được triển khai trong thư viện của ứng dụng. stopAndCloseNativeEngine() cần dừng worker, giải phóng tài nguyên và bảo đảm không còn thread nào sử dụng handle sau khi hàm trả về.

Điểm quan trọng là Java không chỉ lưu một con số nativeHandle. Handle đó đại diện cho trạng thái do thư viện native quản lý. Trước checkpoint, ứng dụng gọi API của thư viện để đóng trạng thái cũ và đặt field Java về giá trị không hợp lệ. Sau restore, ứng dụng tạo handle mới dựa trên cấu hình còn hiệu lực.

Trong ứng dụng thực tế, cần bảo vệ việc sử dụng handle khỏi race condition. Không được đóng handle trong khi một thread khác vẫn đang gọi native method với handle đó. Có thể dùng cơ chế quiesce, lock, reference counting hoặc API lifecycle của thư viện để đảm bảo điều này.

### 7.2. Tại sao không chỉ giữ nguyên con trỏ?

Một con trỏ native là địa chỉ trong không gian địa chỉ của tiến trình. Sau restore, vùng nhớ có thể được khôi phục, nhưng tính hợp lệ của con trỏ còn phụ thuộc vào:

- Vùng nhớ được cấp phát có còn tồn tại không.
- Thư viện sở hữu vùng nhớ có còn ở trạng thái nhất quán không.
- Con trỏ có trỏ đến kernel object hoặc tài nguyên bên ngoài đã hết hạn không.
- Thư viện có yêu cầu khởi tạo lại hoặc đăng ký callback nội bộ không.
- Các thread khác có còn sử dụng vùng nhớ đó không.

Không nên coi con trỏ là một định danh bền vững có thể dùng ở bất kỳ môi trường nào. Nếu thư viện có API tạo và hủy handle, hãy dùng đúng API đó trong lifecycle CRaC.

### 7.3. Phối hợp với thư viện không cung cấp CRaC Resource

Nhiều thư viện native không biết CRaC tồn tại. Ứng dụng có thể cần viết một adapter Resource bao quanh thư viện, hoặc dùng integration do nhà cung cấp thư viện cung cấp.

Adapter nên:

1. Gọi API dừng công việc và đóng tài nguyên trước checkpoint.
2. Ghi nhận cấu hình cần thiết để tạo lại tài nguyên.
3. Sau restore, nạp lại hoặc khởi tạo lại thư viện nếu cần.
4. Tạo lại handle, worker và kết nối.
5. Xác nhận thư viện đã sẵn sàng trước khi ứng dụng nhận yêu cầu.

Nếu thư viện không có API dừng hoặc phục hồi an toàn, cần đánh giá xem nó có tương thích với mô hình checkpoint/restore hay không. Không nên đoán trạng thái nội bộ của thư viện từ các field Java bên ngoài.

## 8. Trình tự chuẩn bị và phục hồi một tài nguyên nhiều lớp

Một tài nguyên có thể gồm object Java, native handle và socket kernel. Ví dụ một native database client có thể có:

- Java wrapper giữ cấu hình và handle.
- Native library quản lý connection pool.
- Kernel quản lý socket.
- Database server quản lý phiên và transaction.

Khi chuẩn bị checkpoint, ứng dụng cần đi theo quyền sở hữu tài nguyên:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant R as CRaC Resource
    participant N as Native library
    participant OS as OS / kernel
    participant DB as Database

    App->>R: beforeCheckpoint()
    R->>N: Stop accepting work
    N->>DB: Finish or cancel in-flight work
    N->>OS: Close sockets and native handles
    N-->>R: Native state released
    R-->>App: Resource prepared
    Note over App,DB: Checkpoint captures the process after preparation
    Note over App,DB: Restore reconstructs the process in a compatible environment
    App->>R: afterRestore()
    R->>N: Initialize native client
    N->>OS: Open new sockets
    N->>DB: Establish new session
    DB-->>N: Session ready
    N-->>R: Native client ready
    R-->>App: Resource available
~~~

Đây là trình tự khái niệm. Thứ tự callback giữa nhiều resource cần tuân theo hợp đồng của CRaC và integration cụ thể. Nếu một resource phụ thuộc vào resource khác, hãy thiết kế quan hệ phụ thuộc rõ ràng thay vì dựa vào thứ tự đăng ký ngầm định.

## 9. Những lỗi thường gặp khi không phân biệt các lớp trạng thái

### 9.1. Object wrapper còn nhưng tài nguyên đã mất

Ứng dụng thấy field connection khác null và cho rằng kết nối vẫn hoạt động. Thực tế, socket đã bị đóng hoặc server đã timeout.

**Cách xử lý:** kiểm tra trạng thái kết nối và tạo lại connection pool sau restore. Không dùng việc object tồn tại làm bằng chứng rằng tài nguyên bên ngoài còn hợp lệ.

### 9.2. Native handle vẫn giữ giá trị cũ

Field long handle vẫn chứa một số khác 0, nhưng thư viện đã giải phóng tài nguyên hoặc handle không còn hợp lệ.

**Cách xử lý:** đóng handle qua API của thư viện trước checkpoint, đặt field về trạng thái invalid và tạo handle mới sau restore.

### 9.3. Đóng file descriptor từ sai tầng

Java tự gọi thao tác đóng descriptor trong khi native library vẫn lưu descriptor đó và tiếp tục sử dụng.

**Cách xử lý:** để thành phần sở hữu descriptor đóng nó. Nếu cần phối hợp giữa Java và native, cung cấp một hàm lifecycle rõ ràng ở phía native.

### 9.4. Native worker vẫn chạy trong lúc checkpoint

Một native thread đang đọc socket hoặc sửa dữ liệu trong buffer. Java Resource chỉ đóng object wrapper mà không dừng worker.

**Cách xử lý:** adapter phải gọi API dừng worker và đợi worker đạt trạng thái an toàn. Chỉ giải phóng native memory sau khi chắc chắn không còn thread sử dụng nó.

### 9.5. Giả định hệ thống từ xa bị đóng băng cùng tiến trình

Ứng dụng khôi phục rồi tiếp tục transaction hoặc message processing như thể database và broker chưa từng thay đổi.

**Cách xử lý:** hoàn tất hoặc hủy thao tác trước checkpoint, xác minh trạng thái sau restore và thiết kế retry có tính idempotent.

### 9.6. Dùng shutdown hook để chuẩn bị checkpoint

Shutdown hook được thiết kế cho quá trình JVM shutdown thông thường. Không nên dùng nó thay cho callback CRaC để chuẩn bị resource.

**Cách xử lý:** đăng ký Resource và đặt logic cần thiết trong beforeCheckpoint() và afterRestore(). Giữ shutdown hook cho quy trình shutdown thực sự của ứng dụng.

### 9.7. Chỉ thử trên môi trường phát triển

Một thư viện native có thể hoạt động trên máy phát triển nhưng thất bại trong container production do khác kernel, mount, quyền, thiết bị hoặc phiên bản thư viện.

**Cách xử lý:** kiểm thử checkpoint và restore trong môi trường gần với production, bao gồm cấu hình container, quyền hệ thống và các dịch vụ mà ứng dụng cần kết nối.

## 10. Cách khảo sát ranh giới trạng thái trước khi áp dụng CRaC

Nên lập danh mục tài nguyên theo từng thành phần của ứng dụng. Với mỗi tài nguyên, ghi nhận chủ sở hữu, lớp trạng thái và cách xử lý vòng đời.

| Thành phần | Java state | Native state | OS / external state | Hành động trước checkpoint | Hành động sau restore |
|---|---|---|---|---|---|
| JDBC pool | Pool object, config | Có thể có native driver state | TCP socket, DB session | Dừng pool, xử lý transaction, đóng connection theo integration | Khởi động pool, xác minh DB |
| HTTP client | Client object, cache | TLS/native provider state tùy thư viện | Socket, DNS, remote server | Dừng request mới, đóng client nếu cần | Tạo lại connection, refresh DNS hoặc credential khi cần |
| Native engine | Java wrapper, handle field | Heap native, worker, static state | File descriptor, shared memory, device | Dừng worker, gọi native cleanup | Tạo engine và handle mới |
| File watcher | Java watcher object | Native event loop tùy implementation | inotify descriptor, file system | Dừng watcher theo API | Tạo watcher mới và đồng bộ trạng thái file |
| Scheduler | Task registry, Java thread | Có thể dùng native timer | Timer, thời gian hệ thống | Pause scheduler, xử lý task đang chạy | Tính lại lịch và resume |
| Message consumer | Consumer object, offset cache | Native client buffer nếu có | Broker connection, committed offset | Ngừng poll, xử lý message đang chạy, commit theo chính sách | Tạo consumer mới, đọc lại offset và resume |

Một quy trình khảo sát có thể thực hiện như sau:

1. Tìm các điểm gọi JNI, JNA, FFM và các thư viện native được nạp.
2. Tìm các API tạo tài nguyên: socket, file, thread, executor, scheduler, direct buffer, native handle.
3. Xác định lớp sở hữu tài nguyên và API đóng/mở chính thức.
4. Xác định tài nguyên có thể tồn tại trong thời gian checkpoint hay cần được đóng.
5. Viết Resource hoặc dùng integration tương thích với CRaC.
6. Thử checkpoint khi tải thấp, rồi tăng dần mức độ đồng thời.
7. Restore sau một khoảng thời gian đủ dài để phát hiện timeout, token hết hạn và trạng thái từ xa thay đổi.
8. Đo thời gian callback, lỗi phục hồi, bộ nhớ native và số lượng kết nối sau restore.

Không phải mọi tài nguyên đều cần đóng trước checkpoint. Một số tài nguyên được nền tảng hỗ trợ khôi phục và có thể được giữ lại. Tuy nhiên, quyết định đó phải dựa trên tài liệu của JDK, CRIU, hệ điều hành và thư viện đang dùng, cùng kết quả thử nghiệm thực tế.

## 11. Bảo mật và tính toàn vẹn của checkpoint

Checkpoint có thể chứa nhiều dữ liệu hơn một tệp cấu hình thông thường. Nó có thể chứa:

- Token truy cập và refresh token.
- Mật khẩu hoặc secret đã giải mã.
- Dữ liệu người dùng trong heap.
- Khóa mã hóa hoặc trạng thái của security provider.
- Dữ liệu tạm thời trong native memory.
- Thông tin kết nối và trạng thái phiên.

Do đó, checkpoint cần được bảo vệ như một artifact chứa dữ liệu nhạy cảm:

- Giới hạn quyền đọc, ghi và phân phối.
- Mã hóa khi lưu trữ hoặc truyền tải theo chính sách của môi trường.
- Không đưa checkpoint vào nơi lưu trữ công khai.
- Quản lý vòng đời và xóa checkpoint cũ.
- Kiểm tra credential sau restore và thu hồi hoặc làm mới khi cần.
- Tránh tạo checkpoint khi ứng dụng đang giữ dữ liệu không nên lưu lâu dài trong bộ nhớ.

Tính toàn vẹn cũng quan trọng. Nếu checkpoint được tạo khi transaction đang dở dang hoặc native buffer chứa dữ liệu chưa đồng bộ, restore có thể tiếp tục từ một trạng thái không nhất quán. Ứng dụng phải xác định các điểm an toàn trước khi cho phép checkpoint.

## 12. Checklist thiết kế Resource cho ứng dụng có mã native

Khi một thành phần sử dụng JNI, JNA, FFM hoặc thư viện native, hãy xác nhận các điểm sau trong quá trình thiết kế:

- [ ] Đã liệt kê các native library được nạp và phiên bản/ABI tương ứng.
- [ ] Đã xác định native memory, native global state và native handle mà thư viện tạo ra.
- [ ] Đã xác định thư viện có tạo native thread, event loop hoặc timer hay không.
- [ ] Đã xác định file descriptor, socket, shared memory và kernel object mà thư viện sở hữu.
- [ ] Có API chính thức để dừng worker và giải phóng tài nguyên trước checkpoint.
- [ ] Không còn thread sử dụng native memory hoặc handle khi resource đã đóng.
- [ ] Sau restore, handle được tạo lại hoặc xác minh bằng API của thư viện.
- [ ] Các kết nối đến database, broker và remote service được xác minh hoặc tạo lại.
- [ ] Callback không dựa vào shutdown hook hoặc finalizer để xử lý checkpoint.
- [ ] Có kiểm thử restore trong môi trường tương thích với production.
- [ ] Checkpoint được bảo vệ như dữ liệu nhạy cảm.

## 13. Kết luận

Trạng thái của một ứng dụng Java trải qua nhiều lớp. Java heap chứa object và dữ liệu ứng dụng; JVM quản lý class, thread và runtime; mã native có thể giữ bộ nhớ, con trỏ, thread và trạng thái thư viện; hệ điều hành quản lý file descriptor, socket, timer, namespace và kernel object; các hệ thống từ xa tiếp tục duy trì trạng thái độc lập với tiến trình.

CRaC giúp lưu và khôi phục trạng thái tiến trình trong một môi trường tương thích. Nhưng mỗi lớp có vòng đời và chủ sở hữu riêng. Một object Java được khôi phục không chứng minh rằng native handle, socket hay phiên database mà nó đại diện vẫn dùng được.

Thiết kế CRaC tốt bắt đầu bằng việc lập bản đồ tài nguyên, xác định ai sở hữu từng tài nguyên và dùng callback để chuẩn bị hoặc khởi tạo lại chúng. Với mã native, cần phối hợp qua API chính thức của thư viện, dừng native worker an toàn và tạo lại handle khi cần. Với tài nguyên hệ điều hành và hệ thống từ xa, cần kiểm tra khả năng tương thích, xác minh trạng thái và thiết lập lại kết nối sau restore.
