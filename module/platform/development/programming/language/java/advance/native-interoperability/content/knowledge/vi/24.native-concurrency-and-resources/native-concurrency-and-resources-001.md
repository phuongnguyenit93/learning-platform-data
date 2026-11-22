# Quy định thư viện native: gọi đồng thời an toàn hay phải dùng một luồng?

Khi Java gọi một thư viện native qua JNI, JNA hoặc Foreign Function & Memory API (FFM), **khả năng gọi đồng thời do chính thư viện native và từng tài nguyên của nó quyết định**. Việc mã Java dùng nhiều thread, dùng một wrapper có đối tượng immutable hay có cơ chế quản lý bộ nhớ an toàn không tự động làm cho hàm C/C++ ở phía dưới trở nên thread-safe.

Mục tiêu của bước tích hợp là viết ra một **hợp đồng đồng thời (concurrency contract)** có thể kiểm tra được: hàm nào được gọi song song, trên handle nào, từ thread nào; ai quản lý khởi tạo/đóng tài nguyên; callback có được gọi ngược vào thư viện không; và chương trình sẽ xử lý ra sao khi hủy, timeout hoặc shutdown.

## 1. Phân biệt các chính sách dễ bị nhầm lẫn

| Chính sách thư viện | Điều được phép | Cách tích hợp thường dùng |
| --- | --- | --- |
| **Thread-safe / concurrent** | Những lời gọi được tài liệu xác nhận có thể thực hiện song song trong phạm vi được nêu | Cho phép gọi trực tiếp; vẫn phối hợp vòng đời đối tượng và shared state |
| **Serialized toàn thư viện** | Tại một thời điểm chỉ một lời gọi vào thư viện, kể cả khi dùng nhiều handle | Một khóa dùng chung cho toàn bộ wrapper hoặc một hàng đợi thực thi |
| **Serialized theo handle/context** | Các handle khác nhau có thể chạy song song; cùng một handle chỉ được một lời gọi tại một thời điểm | Một khóa hoặc một hàng đợi cho mỗi handle; quản lý việc đóng cùng khóa |
| **Thread-confined / thread-affine** | Một handle phải được tạo, sử dụng và hủy trên **cùng thread sở hữu**; đôi khi toàn bộ thư viện buộc dùng một thread xác định | Gán owner thread và chuyển mọi thao tác đến executor/dispatcher của thread đó |
| **Main-thread-only** | Chỉ được gọi trên main/UI/event thread do môi trường native quy định | Dispatch đến đúng thread/framework; executor tự tạo không thay thế được main thread |
| **Non-reentrant** | Không được vào lại cùng hàm/trạng thái khi một lời gọi trước chưa kết thúc, kể cả từ callback cùng thread | Cấm hoặc hoãn gọi lại; kiểm soát đường callback, không chỉ thêm khóa |

**Khác biệt cốt lõi:** “mỗi lần chỉ có một lời gọi” chỉ nói về **sự chồng lấn theo thời gian**; “chỉ một thread” còn nói về **danh tính thread**. Một khóa Java có thể tuần tự hóa hai lần gọi từ thread A rồi thread B, nhưng **không biến B thành A**. Vì thế khóa không đủ cho API có thread affinity.

Cũng cần phân biệt “thread-safe” với “reentrant”: một API có thể cho nhiều thread gọi trên các context độc lập, song không cho callback gọi lại vào chính context đang xử lý. Ngược lại, một hàm có thể reentrant nhưng vẫn truy cập global state không được đồng bộ khi chạy trên các thread khác nhau.

## 2. Phải xác định phạm vi lời bảo đảm

Trước khi thiết kế wrapper, đọc tài liệu đúng **phiên bản thư viện, hệ điều hành, backend và hàm** đang dùng. Những phát biểu như “library is thread-safe” chỉ hữu ích khi biết chính xác điều gì được bảo đảm.

Đối với mỗi nhóm hàm, làm rõ:

1. **Phạm vi trạng thái:** dữ liệu nằm trong process-global singleton, static buffer, một session/context/handle, thread-local storage (TLS), hay bộ nhớ do Java truyền vào?
2. **Đọc/ghi:** hai thao tác chỉ đọc có thể chạy đồng thời không? Đọc có đụng trạng thái cache/lazy initialization? Việc ghi cấu hình có cần độc quyền không?
3. **Độc lập handle:** hai handle có thật sự độc lập, hay cùng dùng bộ allocator, device, global error buffer, registry hoặc kết nối native?
4. **Thread sở hữu:** handle có được chuyển sang thread khác giữa các lần gọi không? Hàm create, use, destroy, callback có cùng ràng buộc không?
5. **Khởi tạo/đóng:** init/shutdown là toàn process, singleton, per-thread hay per-handle? Có được init/close khi vẫn còn call đang chạy không?
6. **Callback:** thư viện gọi callback từ chính thread gọi, thread nội bộ, hay thread do nó tự tạo? Có được gọi ngược API từ callback không?
7. **Lỗi và hủy:** error message/last-error có là TLS không? Call bị hủy hoặc timeout có còn sử dụng handle/buffer ở phía native không?

Ví dụ, câu “nhiều context được xử lý song song” **không suy ra** “cùng context được xử lý song song”. Tương tự, “hàm process thread-safe” **không suy ra** “gọi destroy trong khi process đang chạy là an toàn”.

Nếu tài liệu không nói rõ, ghi chính sách là **unknown** và xác minh qua tài liệu chính thức, header, ví dụ của nhà cung cấp hoặc trao đổi với bên sở hữu thư viện. Khi chưa xác minh, có thể chọn tuần tự hóa thận trọng để giảm rủi ro trong lúc tích hợp, nhưng không công bố đó là bảo đảm thread-safe thực sự. Stress test không thay thế hợp đồng từ tác giả thư viện.

## 3. Chọn ranh giới đồng bộ đúng với trạng thái native

Giả sử thư viện cung cấp các hàm dạng khái niệm:

~~~c
NativeHandle *native_create(void);
int native_process(NativeHandle *handle, const unsigned char *data, size_t length);
void native_destroy(NativeHandle *handle);
~~~

Đây là **chữ ký minh họa**, không phải API của một thư viện có thật. Tùy hợp đồng, cùng ba hàm trên có thể cần ba thiết kế khác nhau:

- Nếu **tất cả handle chia sẻ trạng thái toàn process không an toàn**, phải khóa chung cả create/process/destroy và các hàm đụng trạng thái đó.
- Nếu **mỗi handle có trạng thái độc lập nhưng không thể dùng đồng thời**, dùng khóa riêng từng handle. Hai handle khác nhau được xử lý song song chỉ khi tài liệu cho phép.
- Nếu **handle gắn với thread tạo ra nó**, tạo, xử lý và hủy handle trong cùng một thread sở hữu; dùng hàng đợi để nhận yêu cầu từ các thread Java khác. Khóa quanh từng lời gọi không giải quyết được ràng buộc này.

Một lỗi phổ biến là khóa riêng lời gọi process nhưng cho destroy chạy ngoài khóa. Khi đó thread A có thể đang thực thi process(handle), còn thread B giải phóng handle; hệ quả có thể là use-after-free, crash JVM hoặc hỏng bộ nhớ. **Vòng đời handle là một phần của chính sách đồng thời.**

## 4. Chính sách tuần tự hóa: dùng khóa khi thư viện cho phép đổi thread

Nếu thư viện cho phép các lần gọi kế tiếp ở những thread khác nhau nhưng cấm chồng lấn, một adapter có thể đặt khóa đúng phạm vi trạng thái native:

~~~java
// Đoạn minh họa bên trong một lớp adapter; chưa phải chương trình độc lập.
private final Object nativeLock = new Object();

public int process(long handle, byte[] data) {
    synchronized (nativeLock) {
        ensureOpen(handle);
        return nativeProcess(handle, data); // Binding native được khai báo ở nơi khác.
    }
}

public void destroy(long handle) {
    synchronized (nativeLock) {
        ensureOpen(handle);
        nativeDestroy(handle);
        markClosed(handle);
    }
}
~~~

Khóa trên là **global cho một instance adapter**. Nó chỉ tương đương khóa toàn thư viện nếu mọi đường truy cập thư viện đều đi qua **cùng instance/cùng khóa**. Nếu ứng dụng tạo nhiều adapter, dùng nhiều binding hoặc native có global state dùng chung với mã khác, phải tổ chức một khóa dùng chung theo phạm vi thực tế của thư viện. Đối với API chỉ cần serialize theo handle, sử dụng khóa nằm trong đối tượng sở hữu handle để không chặn nhầm các handle độc lập.

Giữ khóa trong toàn bộ khoảng thời gian native dùng handle và buffer. Không giữ khóa trong những tác vụ Java không liên quan. Đặt thứ tự lấy nhiều khóa nhất quán; tránh gọi ngược ứng dụng tùy ý khi đang giữ khóa, vì callback hoặc listener có thể tạo vòng chờ.

**Không dùng khóa Java để sửa một API yêu cầu cùng OS thread.** Java synchronized hay ReentrantLock bảo đảm loại trừ đồng thời, không bảo đảm thread identity.

## 5. Chính sách một thread: đưa cả vòng đời vào owner executor

Với API yêu cầu handle chỉ được tạo, dùng và hủy trên cùng thread, một single-thread executor là cách triển khai phổ biến trong ứng dụng Java chạy nền. Nhiều caller Java có thể gửi việc đến gateway; gateway lần lượt thực hiện mọi thao tác native trên một thread.

Ví dụ Java 17 sau **chạy độc lập**. Phần native được mô phỏng bằng biến đếm để người học kiểm tra cơ chế thread confinement mà không cần thư viện C hoặc JNI. Trong tích hợp thật, thay các thao tác mô phỏng bằng lời gọi binding và giữ nguyên ràng buộc owner thread.

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class NativeCallPolicyDemo implements AutoCloseable {
    private final ExecutorService owner = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "native-owner"));
    private final Object lifecycle = new Object();

    private volatile Thread ownerThread;
    private boolean closed;              // Chỉ truy cập dưới khóa lifecycle.
    private int simulatedNativeCounter;  // Chỉ truy cập trên owner thread.

    public NativeCallPolicyDemo() throws InterruptedException, ExecutionException {
        owner.submit(() -> {
            ownerThread = Thread.currentThread();
            simulatedNativeCounter = 0;  // Giả lập nativeCreate().
        }).get();
    }

    private void rejectOwnerReentry() {
        if (Thread.currentThread() == ownerThread) {
            throw new IllegalStateException("Blocking reentry from native-owner");
        }
    }

    public int increment(int delta) throws InterruptedException, ExecutionException {
        rejectOwnerReentry();
        Future<Integer> result;
        synchronized (lifecycle) {
            if (closed) {
                throw new IllegalStateException("Gateway closed");
            }
            result = owner.submit(() -> {
                if (Thread.currentThread() != ownerThread) {
                    throw new IllegalStateException("Wrong native thread");
                }
                simulatedNativeCounter += delta; // Giả lập nativeProcess(delta).
                return simulatedNativeCounter;
            });
        }
        return result.get();
    }

    @Override
    public void close() throws InterruptedException, ExecutionException {
        rejectOwnerReentry();
        Future<?> cleanup;
        synchronized (lifecycle) {
            if (closed) {
                return;
            }
            closed = true;
            cleanup = owner.submit(() -> {
                simulatedNativeCounter = 0; // Giả lập nativeDestroy().
            });
        }
        try {
            cleanup.get();
        } finally {
            owner.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (NativeCallPolicyDemo gateway = new NativeCallPolicyDemo()) {
            System.out.println(gateway.increment(1));
            System.out.println(gateway.increment(2));
        }
    }
}
~~~

Lưu vào tệp **NativeCallPolicyDemo.java**, rồi chạy:

~~~bash
javac NativeCallPolicyDemo.java
java NativeCallPolicyDemo
~~~

Đầu ra xác định:

~~~text
1
3
~~~

**Vì sao ví dụ đáp ứng quy tắc một thread?**

- Constructor gửi thao tác tạo đến executor; mỗi lần increment cũng chạy trên thread đó; close xếp thao tác hủy vào cùng hàng đợi.
- Khóa lifecycle bảo đảm các tác vụ đã nhận vào hàng đợi **đứng trước** tác vụ hủy và ngăn nhận lời gọi mới sau khi bắt đầu đóng. Nó không thay thế owner executor.
- ownerThread được ghi nhận một lần; đoạn kiểm tra thread nhằm phát hiện lỗi tích hợp. Biến trạng thái mô phỏng chỉ được owner thread truy cập.
- rejectOwnerReentry ngăn một callback đang chạy trên owner thread gọi increment/close rồi tự chờ Future.get(), gây deadlock: executor không thể thực thi tác vụ mới khi thread của nó đang chờ chính tác vụ ấy.
- try-with-resources đưa thao tác đóng vào vòng đời đối tượng. Các caller khác có thể gọi gateway, nhưng **thứ tự các lời gọi từ các caller đồng thời không được bảo đảm**; ứng dụng phải định nghĩa thứ tự nghiệp vụ nếu cần.

Đây là ví dụ đồng bộ nhằm minh họa chính sách. Trong hệ thống thật, dùng API bất đồng bộ (ví dụ CompletableFuture) hoặc dispatcher phù hợp để tránh chặn UI/event loop; có quy trình xử lý lỗi khi khởi tạo thất bại, kiểm soát shutdown, timeout và thread bị kẹt trong native call. Nếu thư viện yêu cầu **main thread do framework chỉ định**, không thay thế bằng executor tự tạo tên native-owner.

## 6. JNI, JNA và FFM không quyết định thread safety thay thư viện

### JNI

Java có thể gọi cùng phương thức native từ nhiều Java thread cùng lúc. JNI không tự thêm một mutex bao quanh mã C/C++. Con trỏ **JNIEnv*** thuộc về thread JNI đang thực thi; không lưu một JNIEnv* toàn cục rồi dùng từ thread khác. Nếu một thread do native tạo cần gọi Java, nó phải được gắn (attach) vào JVM trước khi sử dụng JNI, lấy JNIEnv* cho chính thread đó và detach phù hợp khi thread kết thúc nếu chính native đã attach. Local JNI references cũng có phạm vi và thời gian sống riêng; khi cần giữ tham chiếu qua lời gọi, phải quản lý global reference đúng quy tắc.

Những yêu cầu này là quy tắc **JNI/JVM**, khác với việc hàm C có an toàn khi chạy song song hay không. Một hàm JNI được gọi với JNIEnv* hợp lệ vẫn có thể gây data race trong thư viện C.

### JNA

JNA giúp ánh xạ hàm và kiểu dữ liệu native vào Java, nhưng việc tạo binding và gọi phương thức trên proxy **không chứng minh** thư viện C đã thread-safe. Quyết định serialize toàn thư viện, theo handle hay dispatch đến owner thread vẫn phải dựa trên contract của thư viện. Khi có callback, phải xét thread gọi callback và khả năng lời gọi quay lại adapter đang giữ khóa.

### Foreign Function & Memory API (FFM)

FFM là API chuẩn từ **JDK 22**; không dùng cú pháp FFM JDK 22 như thể đã có sẵn trên Java 17. Downcall từ Java vào hàm native không sửa được data race của chính hàm đó. Với bộ nhớ ngoài heap, **Arena.ofConfined()** có ràng buộc truy cập theo thread sở hữu, còn **Arena.ofShared()** cho phép truy cập từ nhiều thread nhưng không bảo đảm thư viện native tự đồng bộ. Cần phối hợp cả **quy tắc truy cập/vòng đời memory segment** và **quy tắc đồng thời của native function**; một quy tắc không thay thế quy tắc còn lại.

## 7. Callback, reentrancy, timeout và đóng tài nguyên

### Callback có thể phá vỡ giả định “chỉ gọi từ một nơi”

Một tình huống dễ deadlock:

1. Thread A giữ khóa Java và gọi nativeProcess().
2. Native code gọi callback Java trước khi trả về.
3. Callback Java gọi một API khác cần chính tài nguyên đang xử lý, hoặc chờ một công việc được đưa vào owner executor mà thread hiện tại đang chiếm.
4. Native call chưa thể kết thúc vì callback đang chờ; callback cũng không thể hoàn thành vì tài nguyên/owner thread chưa được giải phóng.

Hợp đồng phải nói rõ callback **có được reenter thư viện không**. Nếu không, callback nên ghi nhận sự kiện, sao chép dữ liệu còn hiệu lực nếu cần, rồi chuyển xử lý tiếp sang hàng đợi khác khi native call đã trở về. Không mặc định rằng khóa reentrant của Java làm native API trở nên reentrant. Nếu callback đến từ thread native tự tạo, xác minh cơ chế attach JVM và phạm vi dữ liệu callback.

### Timeout không có nghĩa là native đã ngừng làm việc

Với Future.get(timeout), hết thời gian chờ chỉ nói **caller không chờ thêm**. Gọi Future.cancel(true) cũng không bảo đảm chặn được một hàm C đang chạy: native code có thể không phản hồi interrupt của Java. Vì vậy không được giải phóng handle, memory segment, callback hoặc input buffer chỉ vì Java nhận TimeoutException. Chỉ dọn dẹp khi có xác nhận call đã kết thúc hoặc cơ chế hủy được thư viện định nghĩa rõ. Nếu thư viện có thể treo vĩnh viễn, có thể cần cách ly trong process phụ để có ranh giới phục hồi mạnh hơn.

### Đóng phải đi cùng chính sách gọi

Xác định khi nào adapter chuyển từ OPEN sang CLOSING rồi CLOSED; từ chối thao tác mới; đợi các thao tác đã nhận hoàn tất; hủy trên đúng thread theo đúng thứ tự. Với khóa theo handle, close phải dùng cùng khóa đó. Với owner executor, close phải được xếp hàng sau các task đã chấp nhận. Không gọi shutdown toàn thư viện khi vẫn còn handle hoặc lời gọi sống, trừ khi tài liệu cho phép.

### Buffer và quyền sở hữu dữ liệu

Ngay cả khi native API thread-safe, Java caller vẫn có thể gây race bằng cách cùng sửa một byte[] hoặc ByteBuffer mà native đang đọc. Tài liệu cần chỉ rõ native **sao chép dữ liệu ngay** hay **giữ con trỏ để dùng sau**, ai sở hữu vùng nhớ, và lúc nào được sửa hoặc giải phóng. Đối với thao tác bất đồng bộ, giữ dữ liệu và handle sống cho đến khi native xác nhận hoàn tất.

## 8. Viết hợp đồng rõ ràng tại ranh giới Java–native

Một wrapper nên có tài liệu cụ thể theo nhóm thao tác, chẳng hạn:

| Thành phần | Ví dụ hợp đồng cần khai báo |
| --- | --- |
| Khởi tạo | Gọi một lần trong process, trước mọi handle; có khóa nếu cần |
| Tạo handle | Trên owner thread hay bất kỳ thread nào? Có được tạo song song? |
| Đọc/ghi handle | Đọc–đọc, đọc–ghi, ghi–ghi có được song song trên **cùng handle** không? |
| Các handle khác nhau | Độc lập thực sự hay dùng khóa global chung? |
| Callback | Thread nguồn, thời hạn dữ liệu, cho phép/cấm reentrancy |
| Hủy handle | Chỉ khi không còn call đang chạy, trên đúng owner thread nếu required |
| Shutdown | Đóng toàn bộ handle, đợi callback/call hoàn tất, rồi mới shutdown |
| Timeout/hủy | Cơ chế hủy native có bảo đảm gì? Caller được phép đóng khi nào? |

Có thể diễn đạt policy ngay trong Javadoc của adapter:

~~~java
/**
 * Quy tắc ví dụ (chỉ dùng khi tài liệu native xác nhận):
 * - Mỗi Handle chỉ có một thao tác native tại một thời điểm.
 * - Hai Handle độc lập được xử lý song song.
 * - close() chờ thao tác đang chạy của cùng Handle kết thúc.
 * - Không gọi lại API của Handle từ native callback.
 * - Không có ràng buộc phải dùng cùng OS thread.
 */
~~~

Đoạn trên là **mẫu hợp đồng**, không phải kết luận về một thư viện cụ thể. Nếu nhà cung cấp nói “mỗi session phải ở thread khởi tạo”, thay chính sách khóa theo handle bằng owner-thread dispatch và ghi rõ cả create/call/destroy.

Một API Java có thể tránh để caller tự giữ khóa bằng cách đóng gói toàn bộ chính sách trong gateway: caller chỉ nhận phương thức an toàn theo contract, không truy cập trực tiếp handle thô. Tách interface/handle API giúp ngăn đường gọi vòng qua khóa hoặc executor; song nếu native có trạng thái global dùng chung giữa nhiều gateway, phải phối hợp ở phạm vi global đó.

## 9. Kiểm chứng chính sách trước khi dùng trong production

Bắt đầu bằng tài liệu/hợp đồng chính thức; sau đó kiểm chứng implementation của adapter bằng các tình huống có chủ đích:

- **Cùng một handle, nhiều caller:** gửi nhiều thao tác từ các Java thread; xác nhận không có hai call cùng handle chồng lấn khi chính sách cấm.
- **Nhiều handle:** nếu tài liệu cho phép, xác nhận adapter không serialize thừa ở mức global; nếu native có trạng thái global, xác nhận có khóa chung.
- **Thread affinity:** ghi thread ID tại create/use/destroy và kiểm tra chúng khớp nhau; thử gọi sai thread trong môi trường kiểm thử để xác nhận bị từ chối.
- **Vòng đời:** chạy close cùng lúc process, close hai lần, submit sau close, constructor lỗi, shutdown khi hàng đợi còn task; không xuất hiện use-after-free hoặc leak.
- **Callback:** kiểm tra callback phát sinh ngay trong native call, callback từ native worker và tình huống gọi ngược; phát hiện deadlock và giữ dữ liệu quá thời hạn.
- **Timeout:** cố ý cho call lâu hơn thời gian chờ; xác minh tài nguyên không bị hủy khi native vẫn đang dùng.

Log tối thiểu nên có operation, handle ID (không lộ pointer/secret), thread ID/name, thời điểm bắt đầu/kết thúc, trạng thái OPEN/CLOSING/CLOSED và mã lỗi native. Với mã C/C++ tự kiểm soát, có thể bổ sung ThreadSanitizer hoặc công cụ phát hiện data race phù hợp; kết quả stress test thành công vẫn **không chứng minh** an toàn cho mọi lịch chạy.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Sửa |
| --- | --- | --- |
| “Wrapper Java là synchronized nên native API đã thread-safe” | Khóa có thể sai phạm vi; direct call khác có thể bypass; thread affinity vẫn bị vi phạm | Xác định scope native rồi bao mọi đường gọi cần thiết |
| Dùng một mutex cho API yêu cầu cùng thread | Hai lần gọi tuần tự vẫn có thể chạy trên hai OS thread khác nhau | Dùng đúng owner thread/dispatcher cho create–use–destroy |
| Khóa process nhưng không khóa destroy | Có thể giải phóng handle khi call đang chạy | Đưa close vào cùng cơ chế điều phối và vòng đời |
| Dùng lock riêng mỗi wrapper khi native có global state | Hai wrapper khác nhau vẫn gọi song song vào global state | Một khóa chung ở phạm vi thư viện/process |
| Coi mọi handle đều phụ thuộc nhau | Mất concurrency dù thư viện cho phép handle độc lập | Khóa theo handle khi contract xác nhận |
| Callback gọi đồng bộ lại owner executor | Owner thread chờ chính công việc mình phải thực thi | Cấm reentry đồng bộ, defer sang pha an toàn |
| Timeout rồi giải phóng buffer | Native call có thể còn chạy dù caller đã bỏ chờ | Chờ native hoàn tất/hủy được xác nhận |
| Dùng JNIEnv* của thread A trên thread B | Vi phạm quy tắc JNI về thread | Lấy JNIEnv* của thread hiện tại, attach khi cần |

## 11. Quy tắc lựa chọn nhanh

1. **Đã có bảo đảm rõ rằng các hàm và handle liên quan an toàn khi concurrent?** Cho phép song song trong đúng phạm vi đó; vẫn đồng bộ vòng đời và input buffer chia sẻ.
2. **Chỉ cấm chồng lấn nhưng cho phép lần gọi sau ở thread khác?** Dùng khóa hoặc hàng đợi; chọn khóa **toàn thư viện** hay **theo handle** dựa trên native state.
3. **Bắt buộc cùng thread tạo handle hoặc main thread của framework?** Dispatch mọi thao tác create/use/destroy đến đúng thread; thiết kế callback và close để tránh tự chờ.
4. **Thiếu hoặc mâu thuẫn thông tin?** Giữ policy ở trạng thái chưa được xác minh, ưu tiên hành vi bảo thủ, ghi lại câu hỏi cụ thể cần nhà cung cấp xác nhận trước khi tuyên bố thread-safe.

**Kết luận kỹ thuật:** Chính sách đồng thời phải bám vào **hợp đồng của thư viện native, phạm vi trạng thái và vòng đời tài nguyên**. Java lock giải quyết loại trừ đồng thời; owner-thread executor giải quyết thread affinity; callback và cleanup phải tuân theo cùng chính sách. Chỉ khi các ranh giới này được xác định rõ, adapter Java mới có thể cung cấp API gọi native an toàn và dễ kiểm chứng.
