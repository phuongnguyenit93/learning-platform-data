# Tài nguyên JNI, thư viện native và file descriptor ngoài JDK

Ứng dụng Java có thể sở hữu nhiều tài nguyên nằm ngoài phạm vi quản lý trực tiếp của JDK: socket do thư viện C/C++ mở, file descriptor do JNI tạo, thread native, mutex của POSIX, vùng nhớ ánh xạ bằng `mmap`, handle của thiết bị hoặc context của thư viện tăng tốc. Các tài nguyên này vẫn gắn với tiến trình và hệ điều hành dù phần lớn logic ứng dụng được viết bằng Java.

Khi dùng CRaC, việc JVM chụp được heap và trạng thái tiến trình không đồng nghĩa mọi tài nguyên native đều tiếp tục hoạt động đúng sau restore. Một số tài nguyên có thể được checkpoint engine khôi phục nếu hệ điều hành và loại descriptor hỗ trợ; một số tài nguyên cần đóng trước checkpoint rồi tạo lại sau restore; một số khác không thể phục hồi an toàn và phải được giải phóng hoặc khởi tạo lại theo quy trình riêng.

Vì vậy, ứng dụng cần đưa tài nguyên JNI và thư viện native vào cùng quy trình quản lý vòng đời CRaC. Cách phổ biến là tạo một Java wrapper triển khai `org.crac.Resource` (hoặc API CRaC mà ứng dụng chọn), sau đó gọi các hàm JNI để dừng hoạt động native, giải phóng handle trước checkpoint và mở lại tài nguyên sau restore.

## 1. Phân biệt trạng thái Java, native memory và tài nguyên hệ điều hành

Một tiến trình Java có nhiều lớp trạng thái:

| Loại trạng thái | Ví dụ | Điều cần quan tâm khi checkpoint/restore |
|---|---|---|
| Java heap | Object, collection, trạng thái service | Thường được lưu trong ảnh tiến trình; vẫn cần kiểm tra tính nhất quán nghiệp vụ |
| Native memory thuộc tiến trình | Vùng nhớ `malloc`, cấu trúc C/C++, stack của native thread | Nội dung bộ nhớ có thể nằm trong ảnh tiến trình, nhưng con trỏ tới tài nguyên bên ngoài vẫn có thể lỗi thời |
| Tài nguyên kernel | File descriptor, socket, pipe, eventfd, epoll, file lock | Khả năng khôi phục phụ thuộc loại tài nguyên, OS, checkpoint engine và cấu hình |
| Tài nguyên thiết bị hoặc dịch vụ ngoài | GPU context, camera, audio device, session tới server | Thường cần xác minh, đóng và tạo lại hoặc đăng ký lại sau restore |
| Trạng thái đồng bộ native | `pthread_mutex`, condition variable, native worker thread | Phải dừng ở safe point, tránh thread đang giữ lock hoặc ở giữa thao tác không thể tiếp tục |

Điểm cần nhớ: **bộ nhớ của tiến trình và tài nguyên do kernel hoặc hệ thống bên ngoài quản lý là hai vấn đề khác nhau**. Một con trỏ C có thể vẫn tồn tại trong ảnh bộ nhớ nhưng đối tượng mà nó từng đại diện đã bị đóng, thay đổi hoặc không được phục hồi. Tương tự, một số nguyên lưu số hiệu file descriptor có thể vẫn còn nguyên trong bộ nhớ nhưng descriptor tương ứng không còn trỏ tới tài nguyên đúng.

Ví dụ, thư viện native lưu `socket_fd = 42`. Nếu socket đó được đóng trước checkpoint, sau restore biến `socket_fd` vẫn có thể chứa số 42 nếu code không đặt lại sentinel. Hệ điều hành có thể đã tái sử dụng số 42 cho một file hoặc socket khác. Gọi `send(42, ...)` khi đó có thể ghi nhầm vào tài nguyên mới. Vì thế, khi giải phóng descriptor, phải cập nhật cả trạng thái sở hữu trong thư viện native.

## 2. JNI không tự quản lý vòng đời của tài nguyên native

JNI là cầu nối để Java gọi hàm native và để mã native tương tác với JVM. JNI không tự biết thư viện C/C++ đã mở những file descriptor nào, tạo bao nhiêu thread, đăng ký signal handler nào hoặc đang giữ handle của thiết bị nào.

Một thư viện native có thể khởi tạo trạng thái theo nhiều cách:

- `System.loadLibrary(...)` nạp thư viện vào tiến trình.
- `JNI_OnLoad` chạy khi thư viện được JVM nạp và có thể khởi tạo cấu trúc toàn cục.
- Một native method mở socket, file, device hoặc tạo thread khi ứng dụng bắt đầu sử dụng chức năng.
- Biến `static` trong C/C++ giữ descriptor, pointer, mutex, trạng thái cache hoặc handle dùng chung.
- Thư viện bên thứ ba có thể tự tạo worker thread và kết nối tới dịch vụ ngoài mà Java không nhìn thấy trực tiếp.

CRaC không tự gọi một hàm `JNI_OnLoad` mới chỉ vì tiến trình được restore. Nếu thư viện đã được nạp tại thời điểm checkpoint, trạng thái mapping và biến toàn cục của nó thuộc trạng thái tiến trình. Do đó, không dùng `JNI_OnLoad` làm callback phục hồi sau restore. Hãy tách rõ **nạp thư viện** khỏi **mở tài nguyên runtime** và cung cấp các hàm native có thể gọi lại một cách có kiểm soát.

`JNI_OnUnload` cũng không phải hook phù hợp để dọn tài nguyên trước checkpoint. Nó gắn với vòng đời unload của native library, không phải sự kiện CRaC chuẩn bị chụp tiến trình. Hãy dùng callback `beforeCheckpoint` để chủ động yêu cầu thư viện giải phóng tài nguyên.

### Một số trạng thái native cần kiểm kê

- File descriptor được tạo bằng `open`, `socket`, `accept`, `pipe`, `eventfd`, `epoll_create` hoặc API tương tự.
- Native thread tạo bằng `pthread_create`, thread pool riêng của thư viện hoặc callback chạy nền.
- Mutex, condition variable, semaphore và lock đang được native thread sử dụng.
- Bộ nhớ `mmap`, shared memory, vùng nhớ pinned hoặc buffer do thiết bị cấp.
- Handle của GPU, camera, audio, USB, serial port hoặc thư viện mật mã phần cứng.
- Kết nối và session tới database, broker, RPC server hoặc daemon bên ngoài.
- Signal handler, timer của OS, callback đăng ký với event loop và trạng thái TLS native.

Không phải mọi thư viện đều cung cấp API để đóng và tạo lại các tài nguyên này. Nếu thư viện không có lifecycle hook hoặc không tài liệu hóa khả năng checkpoint/restore, cần đánh giá việc bổ sung adapter, thay thế cách tích hợp hoặc loại thư viện khỏi quy trình checkpoint.

## 3. Đưa native resource vào lifecycle của CRaC

API CRaC cung cấp hợp đồng `Resource` với hai callback chính:

| Callback | Mục tiêu đối với tài nguyên native |
|---|---|
| `beforeCheckpoint(...)` | Dừng nhận việc, đợi native operation kết thúc, dừng worker thread tại safe point, flush dữ liệu cần thiết và đóng những handle không thể giữ qua checkpoint |
| `afterRestore(...)` | Mở lại descriptor hoặc session, tạo lại native worker, khởi tạo lại context thiết bị và xác minh tài nguyên đã sẵn sàng |

Một Java wrapper có thể điều phối các lời gọi JNI như sau:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.crac.Context;
import org.crac.Resource;

final class NativeLibraryResource implements Resource {
    private final NativeBridge nativeBridge;
    private final Duration stopTimeout;

    NativeLibraryResource(
            NativeBridge nativeBridge,
            Duration stopTimeout) {
        this.nativeBridge = nativeBridge;
        this.stopTimeout = stopTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        try {
            nativeBridge.stopAcceptingWork();

            if (!nativeBridge.awaitNativeWork(stopTimeout.toMillis())) {
                throw new TimeoutException(
                        "Native work did not reach a safe point"
                );
            }

            nativeBridge.closeExternalHandles();
        } catch (Exception failure) {
            try {
                nativeBridge.resumeAfterAbortedCheckpoint();
            } catch (Exception resumeFailure) {
                failure.addSuppressed(resumeFailure);
            }
            throw failure;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        nativeBridge.reopenExternalHandles();
        nativeBridge.startNativeWorkers();
    }
}
```

`NativeBridge` là lớp Java do ứng dụng định nghĩa, với các phương thức `native` tương ứng:

```java
final class NativeBridge {
    native void stopAcceptingWork();
    native boolean awaitNativeWork(long timeoutMillis);
    native void closeExternalHandles();
    native void reopenExternalHandles();
    native void startNativeWorkers();
    native void resumeAfterAbortedCheckpoint();
}
```

Ví dụ này mô tả cấu trúc điều phối. Tên phương thức không phải API có sẵn của JNI hay CRaC; phần C/C++ phải triển khai đúng hợp đồng, bao gồm đồng bộ thread, kiểm tra lỗi hệ điều hành và quản lý quyền sở hữu từng handle.

Trong ứng dụng thực tế, hãy đăng ký `NativeLibraryResource` với CRaC global context trong giai đoạn khởi tạo. Nếu có nhiều thư viện native, có thể tạo một lifecycle coordinator quản lý thứ tự dừng và phục hồi thay vì để các thành phần tự ý đóng tài nguyên của nhau.

### Trình tự trong mã native

Một thư viện C có thể duy trì trạng thái như sau:

```c
static int upstream_fd = -1;
static int event_fd = -1;
static bool worker_started = false;
static bool stopping = false;

/* Được gọi từ JNI trước checkpoint. */
void native_prepare_checkpoint(void) {
    stopping = true;
    signal_worker_to_stop();

    if (worker_started) {
        pthread_join(worker_thread, NULL);
        worker_started = false;
    }

    if (upstream_fd >= 0) {
        close(upstream_fd);
        upstream_fd = -1;
    }

    if (event_fd >= 0) {
        close(event_fd);
        event_fd = -1;
    }
}

/* Được gọi từ JNI sau restore. */
void native_restore_resources(void) {
    upstream_fd = connect_to_upstream();
    if (upstream_fd < 0) {
        throw_native_initialization_error();
        return;
    }

    event_fd = create_event_channel();
    if (event_fd < 0) {
        close(upstream_fd);
        upstream_fd = -1;
        throw_native_initialization_error();
        return;
    }

    stopping = false;
    start_worker_thread();
    worker_started = true;
}
```

Đây là mã giả gần với C để minh họa lifecycle, không phải một triển khai JNI hoàn chỉnh. Các hàm `signal_worker_to_stop`, `connect_to_upstream`, `create_event_channel`, `throw_native_initialization_error` và `start_worker_thread` là phần triển khai riêng của thư viện. Khi tích hợp JNI thật, cần chuyển lỗi native thành exception Java phù hợp và bảo đảm không để một nửa tài nguyên được mở mà không có đường cleanup.

## 4. File descriptor do thư viện native tạo

File descriptor (FD) là một số nguyên mà tiến trình dùng để tham chiếu tới một đối tượng I/O của kernel. Java stream hoặc NIO channel cũng có thể dùng FD bên dưới, nhưng bài học này tập trung vào descriptor được mở và sở hữu bởi JNI hoặc thư viện native ngoài JDK.

Các nguồn FD thường gặp:

```c
int file_fd = open("/var/lib/app/state.bin", O_RDWR);
int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
int pipe_fds[2];
pipe(pipe_fds);
int event_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
int epoll_fd = epoll_create1(EPOLL_CLOEXEC);
```

Không thể kết luận mọi FD đều được khôi phục hoặc đều phải đóng. Khả năng restore phụ thuộc vào loại descriptor, kernel, phiên bản CRIU hoặc checkpoint engine, cấu hình container, quyền truy cập và trạng thái của tài nguyên bên ngoài.

| Loại descriptor | Vấn đề khi restore | Hướng xử lý thường dùng |
|---|---|---|
| Regular file | File path, mount, inode, offset và lock có thể thay đổi hoặc không còn phù hợp | Kiểm tra file và mount trong môi trường đích; đóng/mở lại nếu cần |
| TCP socket | Peer có thể đã timeout hoặc trạng thái kết nối không còn phù hợp với dịch vụ bên ngoài | Thường ưu tiên đóng và kết nối lại ở tầng ứng dụng, trừ khi đã kiểm chứng hỗ trợ restore socket cụ thể |
| Unix domain socket | Socket gắn với daemon hoặc endpoint cục bộ có thể không tồn tại khi restore | Kết nối lại tới daemon sau restore |
| Pipe/FIFO | Đầu bên kia có thể đã đóng hoặc tiến trình đối tác không được restore cùng lúc | Tái tạo kênh và bắt tay lại với đối tác |
| `epoll`, `eventfd`, `inotify` | Trạng thái đăng ký và đối tượng kernel liên quan phụ thuộc môi trường | Tạo lại descriptor và đăng ký lại watch/event sau restore nếu cần |
| Device FD | Thiết bị hoặc driver có thể không hỗ trợ khôi phục trạng thái | Đóng trước checkpoint, mở và khởi tạo lại sau restore |
| Shared memory hoặc `mmap` | Backing file, mount, shared mapping và các tiến trình cùng chia sẻ có thể không đồng bộ | Xác minh backing resource và phối hợp với mọi tiến trình liên quan |

### Không nhầm số FD với tài nguyên

Số FD chỉ là chỉ mục trong bảng descriptor của tiến trình. Giá trị `17` không phải danh tính bền vững của socket hoặc file. Sau khi đóng FD, kernel có thể cấp lại chính số đó cho một tài nguyên khác.

Khi đóng FD trong thư viện native, hãy cập nhật trạng thái sở hữu ngay:

```c
if (socket_fd >= 0) {
    close(socket_fd);
    socket_fd = -1;
}
```

Mọi đường truy cập phải kiểm tra trạng thái đã mở trước khi gọi `read`, `write`, `send`, `recv` hoặc `ioctl`. Nếu một FD được chia sẻ giữa nhiều object, cần một chủ sở hữu duy nhất hoặc cơ chế reference counting rõ ràng để tránh double-close và use-after-close.

### Không đóng nhầm FD do JDK sở hữu

Một thư viện native đôi khi nhận FD từ Java hoặc nhận một `FileDescriptor` qua JNI. Khi đó phải xác định rõ quyền sở hữu:

- Nếu Java/JDK là chủ sở hữu, thư viện native chỉ mượn descriptor và không được tự đóng nó.
- Nếu native library tạo FD và chuyển quyền sở hữu cho Java, phải có hợp đồng rõ ràng về thành phần nào chịu trách nhiệm đóng.
- Nếu hai phía cùng giữ tham chiếu, phải xác định việc duplicate descriptor (`dup`) hay chỉ chia sẻ cùng một FD; hai trường hợp có semantics đóng khác nhau.

Đóng một FD mà JDK vẫn nghĩ là đang mở có thể làm hỏng stream/channel Java. Ngược lại, không đóng FD native do ứng dụng sở hữu có thể để lại descriptor cũ trong checkpoint. Hãy quản lý ownership ở một nơi duy nhất.

## 5. Native thread, mutex và trạng thái đồng bộ

Thư viện JNI có thể tạo thread bằng `pthread_create` hoặc dùng thread pool riêng. Các thread này có thể đang:

- Chờ trên condition variable hoặc semaphore.
- Giữ mutex trong lúc cập nhật cấu trúc dữ liệu native.
- Gửi hoặc nhận dữ liệu qua socket.
- Thực hiện callback vào Java bằng JNI.
- Giữ JNI global reference hoặc con trỏ tới buffer do Java cung cấp.
- Chạy trong thư viện bên thứ ba mà ứng dụng không kiểm soát trực tiếp.

Trước checkpoint, nên yêu cầu worker dừng nhận việc, đánh thức thread đang chờ, chờ operation hiện tại hoàn tất và `join` thread nếu lifecycle của thư viện cho phép. Không chụp trạng thái khi một thread đang giữ mutex mà thread khác cần để hoàn tất callback hoặc phục hồi.

Nếu để native thread tồn tại qua checkpoint, phải xác minh rõ runtime và checkpoint engine hỗ trợ loại thread, signal, TLS, stack và trạng thái đồng bộ đó. Việc process restore thành công không chứng minh mọi thread native tiếp tục đúng logic nghiệp vụ. Với thư viện có API stop/start worker, thường dễ kiểm soát hơn khi dừng worker trước checkpoint rồi tạo lại worker sau restore.

Không dùng `pthread_cancel` một cách tùy tiện để ép thread dừng. Cancellation giữa thao tác ghi dữ liệu hoặc khi đang giữ lock có thể để lại cấu trúc native không nhất quán. Ưu tiên cooperative cancellation: đặt cờ dừng, đánh thức worker, cho worker kết thúc ở safe point và chờ hoàn tất.

## 6. Native memory, `mmap` và handle thiết bị

### Bộ nhớ cấp phát trong tiến trình

Bộ nhớ do `malloc` hoặc `new` cấp phát thường nằm trong address space của tiến trình. Nội dung đó có thể được lưu cùng ảnh bộ nhớ khi checkpoint. Tuy nhiên, việc giữ được các byte không đồng nghĩa mọi object native còn hợp lệ:

- Pointer tới một descriptor đã đóng là stale handle.
- Pointer tới vùng nhớ do driver hoặc thiết bị quản lý có thể không còn hợp lệ.
- Một object native có thể chứa mutex hoặc condition variable đang ở trạng thái không an toàn.
- Một thư viện có thể lưu địa chỉ của mapping hoặc tài nguyên được tạo bởi một tiến trình khác.

### Memory mapping và shared memory

Với `mmap`, cần kiểm tra cả mapping lẫn backing resource. Một mapping của file có thể cần cùng file, mount và quyền truy cập sau restore. Shared memory còn có thể được tiến trình khác sử dụng đồng thời; nếu chỉ restore một tiến trình, hai bên có thể không còn thống nhất về version hoặc lock.

Nếu mapping là cache có thể tái tạo, cân nhắc unmap trước checkpoint rồi map lại sau restore. Nếu mapping chứa dữ liệu chia sẻ quan trọng, cần thiết kế giao thức đồng bộ và versioning riêng; không giả định ảnh JVM tự giải quyết nhất quán giữa nhiều tiến trình.

### GPU, camera và thiết bị ngoại vi

Handle của GPU context, CUDA stream, camera, audio device, USB hoặc accelerator thường gắn với driver và trạng thái thiết bị. Không nên giả định chúng có thể được phục hồi chỉ vì pointer vẫn còn trong native memory. Hãy dùng API của thư viện/driver để giải phóng context trước checkpoint và tạo context mới sau restore. Nếu driver không hỗ trợ lifecycle này, hãy loại tài nguyên đó khỏi tiến trình checkpoint hoặc tách chức năng thiết bị sang một service riêng.

## 7. Phối hợp với thư viện native bên thứ ba

Ứng dụng thường không trực tiếp sở hữu code C/C++ của mọi thư viện. Driver database, client message broker, thư viện xử lý ảnh, codec, thư viện mật mã hoặc SDK thiết bị có thể tự mở FD và tạo thread.

Trước khi bật CRaC, hãy xác định:

1. Thư viện có tài liệu về CRaC/checkpoint/restore hay không.
2. Có API để dừng hoạt động, flush, close và reconnect không.
3. Có thread native hoặc timer nội bộ không.
4. Thư viện có dùng file descriptor hoặc device handle mà ứng dụng không truy cập được không.
5. Phiên bản thư viện và driver có nằm trong ma trận môi trường được hỗ trợ không.
6. Có thể kiểm tra trạng thái sau restore và báo lỗi về readiness không.

Nếu thư viện cung cấp lifecycle API riêng, hãy gọi đúng API đó trong callback. Không tự đóng descriptor bằng cách đọc số FD nội bộ hoặc reflection vào implementation không được hỗ trợ; việc đó có thể làm hỏng trạng thái nội bộ và tạo lỗi khó tái hiện.

Nếu thư viện không cung cấp cách tái tạo tài nguyên, các lựa chọn gồm nâng cấp phiên bản, thay thư viện, tạo adapter được vendor hỗ trợ, tách phần native sang process/service khác hoặc không dùng CRaC cho tiến trình đó. Chọn phương án dựa trên khả năng phục hồi thực tế thay vì giả định rằng mọi native state đều được checkpoint engine xử lý.

## 8. Xử lý lỗi và tính lặp an toàn

Các callback có thể gặp lỗi ở cả hai phía:

- `beforeCheckpoint`: không dừng được worker, không drain xong, flush thất bại hoặc đóng descriptor lỗi.
- `afterRestore`: không mở được file, kết nối server thất bại, driver không cấp context, thiếu quyền hoặc thư viện native không tương thích.

Thiết kế lifecycle cần có các nguyên tắc:

- Các hàm close/reopen nên idempotent hoặc có trạng thái rõ ràng để gọi lặp không gây double-close.
- Dùng sentinel như `-1` cho FD chưa mở và cập nhật ngay sau khi đóng.
- Nếu mở nhiều tài nguyên sau restore, khi một bước thất bại phải cleanup các tài nguyên đã mở trước đó.
- Không đánh dấu native subsystem sẵn sàng cho tới khi mọi handle bắt buộc đã được xác minh.
- Chuyển exception lên callback CRaC khi tài nguyên thiết yếu không thể phục hồi.
- Ghi log loại resource và mã lỗi hệ điều hành, nhưng không ghi secret hoặc payload nhạy cảm.
- Có quy trình vận hành để thay instance hoặc rollback khi restore không thể hoàn tất.

Một điểm quan trọng: nếu `beforeCheckpoint` đã hoàn tất và sau đó checkpoint engine thất bại ở giai đoạn tiếp theo, ứng dụng không nên giả định sẽ có một callback CRaC riêng tự động mở lại mọi tài nguyên. Cần phối hợp với cơ chế điều khiển checkpoint của ứng dụng/nền tảng để xử lý thất bại của toàn bộ attempt và đưa instance trở lại trạng thái phục vụ hoặc thay thế nó. Nhánh `catch` trong callback chỉ xử lý được lỗi xảy ra trong phần chuẩn bị mà chính callback đang thực hiện.

## 9. Kiểm thử native resource trên môi trường thực tế

Kiểm thử phải chạy trên đúng loại JDK, OS, kernel, checkpoint engine, container runtime và driver dự kiến dùng khi triển khai. Bài test chỉ xác nhận ứng dụng khởi động lại được là chưa đủ.

Một kịch bản kiểm thử nên gồm:

1. Khởi động ứng dụng và xác nhận native library được nạp.
2. Mở các loại tài nguyên đại diện: file, socket, event channel, mapping hoặc device context.
3. Tạo tải có kiểm soát để native worker đang hoạt động.
4. Yêu cầu checkpoint; xác nhận ứng dụng dừng nhận việc và đợi worker tới safe point.
5. Quan sát callback đóng descriptor và dừng native thread.
6. Thực hiện restore từ checkpoint.
7. Xác nhận callback mở lại tài nguyên, kết nối tới đúng peer và tạo lại worker.
8. Gửi request hoặc công việc mới, kiểm tra không có FD stale, double-close, leak hoặc thao tác ghi nhầm descriptor.
9. Thử trường hợp close/reconnect thất bại để xác nhận readiness không chuyển sang accepting.
10. Thử checkpoint thất bại sau khi chuẩn bị để xác nhận quy trình rollback hoặc thay instance hoạt động đúng.

Các tín hiệu quan sát hữu ích:

| Tín hiệu | Mục đích |
|---|---|
| Số FD trước và sau restore theo loại | Phát hiện rò rỉ hoặc descriptor còn sót |
| Số native worker đang chạy | Xác nhận worker dừng và khởi tạo lại đúng số lượng |
| Thời gian stop/join native thread | Phát hiện worker không tới safe point |
| Kết quả reconnect và mã lỗi OS | Phân biệt lỗi quyền, endpoint, driver hoặc giới hạn checkpoint engine |
| Trạng thái readiness | Bảo đảm ứng dụng chỉ nhận việc sau khi native subsystem sẵn sàng |
| Số lần khởi tạo/đóng resource | Phát hiện double-init, double-close hoặc callback chạy lặp |

## 10. Checklist tích hợp JNI và native library với CRaC

- [ ] Đã lập danh sách native library, FD, native thread, mutex, mapping và device handle mà ứng dụng sử dụng.
- [ ] Đã xác định rõ chủ sở hữu của từng FD; không đóng nhầm descriptor do JDK quản lý.
- [ ] Thư viện có API dừng nhận việc và chờ operation native kết thúc.
- [ ] Native worker dừng ở safe point và không còn giữ lock cần thiết trước checkpoint.
- [ ] Các descriptor không được giữ qua restore đã được đóng và đặt về trạng thái chưa mở.
- [ ] Các resource cần tạo lại có hàm reopen/reinitialize rõ ràng.
- [ ] Không dựa vào `JNI_OnLoad` hoặc `JNI_OnUnload` như callback checkpoint/restore.
- [ ] `afterRestore` xác minh kết nối, driver, mapping và handle trước khi báo sẵn sàng.
- [ ] Các hàm cleanup và initialization có thể xử lý lỗi một phần mà không làm rò rỉ tài nguyên.
- [ ] Có timeout cho việc dừng native worker và có đường phục hồi khi timeout.
- [ ] Đã kiểm thử từng loại FD trên đúng kernel và checkpoint engine.
- [ ] Đã thử restore khi dịch vụ ngoài thay đổi trạng thái hoặc không còn truy cập được.
- [ ] Có metric/log để phát hiện FD leak, native thread bị treo và lỗi khởi tạo sau restore.

## 11. Kết luận

JNI và thư viện native mở rộng khả năng của Java nhưng cũng đưa thêm tài nguyên nằm ngoài vòng đời mà JDK tự quản lý. CRaC chỉ an toàn khi ứng dụng hiểu rõ tài nguyên nào là bộ nhớ tiến trình, tài nguyên nào thuộc kernel và tài nguyên nào gắn với thiết bị hoặc dịch vụ bên ngoài.

Hãy dùng `Resource.beforeCheckpoint(...)` để dừng native work ở safe point, chờ worker hoàn tất và giải phóng các handle cần tạo lại. Dùng `Resource.afterRestore(...)` để mở lại descriptor, tái tạo context và khởi động worker sau khi đã xác minh môi trường. Đối với từng loại FD, thread và thư viện native, phải kiểm thử trên đúng nền tảng triển khai; không suy luận khả năng restore chỉ từ việc dữ liệu Java hoặc con trỏ native vẫn còn trong bộ nhớ.
