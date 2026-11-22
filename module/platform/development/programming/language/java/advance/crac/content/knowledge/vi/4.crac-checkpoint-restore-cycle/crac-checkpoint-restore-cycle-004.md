# Yêu cầu checkpoint bằng jcmd và JDK.checkpoint

Trong CRaC (Coordinated Restore at Checkpoint), ứng dụng có thể lưu trạng thái tiến trình tại một thời điểm để khởi động lại nhanh bằng cách khôi phục trạng thái đã lưu. Để bắt đầu thao tác này, người vận hành có thể gửi yêu cầu từ bên ngoài bằng công cụ jcmd với lệnh chẩn đoán JDK.checkpoint. Mã Java cũng có thể chủ động yêu cầu chu kỳ checkpoint–restore thông qua API CRaC.

Hai cách kích hoạt có chung mục tiêu nhưng nằm ở hai vị trí khác nhau: jcmd gửi lệnh đến một JVM đang chạy, còn API cho phép ứng dụng tự chọn thời điểm thích hợp trong luồng nghiệp vụ. Cả hai đều cần JVM CRaC và quy trình chuẩn bị tài nguyên trước checkpoint.

## 1. Yêu cầu checkpoint là gì?

Checkpoint ghi lại trạng thái của tiến trình để có thể khôi phục sau đó. Trạng thái được lưu có thể bao gồm heap, stack, trạng thái thread và các phần trạng thái tiến trình mà runtime cùng cơ chế checkpoint hỗ trợ.

Checkpoint không đồng nghĩa với việc ứng dụng đã được restore. Đây là hai giai đoạn riêng:

1. **Checkpoint:** JVM phối hợp với các resource đã đăng ký, chuẩn bị tiến trình và tạo ảnh trạng thái.
2. **Restore:** runtime khởi tạo lại tiến trình từ ảnh đã lưu. Ứng dụng tiếp tục từ trạng thái được khôi phục và hoàn tất các bước tái kết nối tài nguyên.

Có thể hình dung chu kỳ như sau:

~~~text
JVM đang phục vụ yêu cầu
        |
        | Nhận yêu cầu checkpoint
        v
Chạy callback beforeCheckpoint
        |
        v
Hoàn tất chuẩn bị và lưu trạng thái
        |
        v
Checkpoint image được tạo
        |
        | Khởi chạy restore từ image
        v
Khôi phục tiến trình
        |
        v
Chạy callback afterRestore
        |
        v
Ứng dụng tiếp tục hoạt động
~~~

Việc tạo checkpoint thường được dùng để chuẩn bị sẵn một tiến trình đã nạp lớp, khởi tạo framework hoặc hoàn tất một số bước khởi động tốn thời gian. Khi cần chạy instance mới, hệ thống có thể restore từ trạng thái đã chuẩn bị thay vì lặp lại toàn bộ quá trình khởi động.

Checkpoint chỉ an toàn khi trạng thái ứng dụng và tài nguyên bên ngoài đã được xử lý phù hợp. Ví dụ, một socket đang kết nối đến máy chủ từ xa, một transaction đang mở hoặc một worker đang cập nhật dữ liệu có thể không còn hợp lệ sau restore. CRaC cung cấp callback để ứng dụng phối hợp xử lý các tình huống đó.

## 2. Điều kiện trước khi gửi yêu cầu

Trước khi chạy lệnh checkpoint, cần xác nhận môi trường đáp ứng các điều kiện sau.

### JVM có hỗ trợ CRaC

Không phải mọi bản phân phối JDK đều hỗ trợ CRaC. Cần dùng bản JDK được xây dựng hoặc cấu hình có hỗ trợ CRaC, đúng phiên bản và hệ điều hành mà ứng dụng sẽ chạy.

Có thể xem phiên bản JVM bằng:

~~~bash
java -version
~~~

Sau đó kiểm tra tài liệu của bản phân phối JDK đang sử dụng để biết cách bật CRaC, các tùy chọn JVM, nền tảng được hỗ trợ và các yêu cầu hệ thống. Một số môi trường CRaC trên Linux sử dụng CRIU (Checkpoint/Restore In Userspace) cùng các quyền và tính năng kernel tương ứng.

### Đã cấu hình nơi lưu checkpoint

Đường dẫn lưu ảnh checkpoint cần được chuẩn bị trước khi khởi chạy JVM. Với nhiều bản JDK CRaC, tùy chọn thường dùng là:

~~~bash
-XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint
~~~

Ví dụ khởi động ứng dụng:

~~~bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint \
  -jar app.jar
~~~

Đường dẫn cần tồn tại hoặc có thể được runtime tạo theo yêu cầu của bản JDK, và tài khoản chạy JVM phải có quyền ghi phù hợp. Nên kiểm tra hướng dẫn của bản JDK cụ thể vì cách cấu hình và hành vi có thể khác giữa các nhà cung cấp.

Không nên lưu checkpoint vào thư mục tạm có thể bị dọn tự động. Ảnh checkpoint có thể lớn và chứa trạng thái bộ nhớ của tiến trình, vì vậy cần dự trù dung lượng đĩa, giới hạn quyền truy cập và chính sách lưu trữ.

### jcmd có thể attach vào JVM đích

jcmd là công cụ JDK dùng để gửi diagnostic command đến một tiến trình Java đang chạy trên cùng máy. Thông thường, người dùng chạy jcmd cần có quyền phù hợp với tài khoản đang chạy JVM đích. Hãy dùng công cụ jcmd thuộc JDK tương thích với JVM mục tiêu và kiểm tra quy tắc attach của hệ điều hành hoặc môi trường container.

Nếu chạy trong container, cần bảo đảm lệnh được thực hiện ở đúng namespace và có thể nhìn thấy tiến trình JVM. Một PID nhìn thấy từ host có thể khác PID bên trong container.

## 3. Gửi yêu cầu bằng jcmd và JDK.checkpoint

JDK.checkpoint là tên một diagnostic command của JVM CRaC. Người vận hành gọi command này thông qua jcmd, truyền vào PID của tiến trình cần checkpoint.

### Bước 1: Tìm PID của ứng dụng

Liệt kê các tiến trình Java mà jcmd có thể phát hiện:

~~~bash
jcmd -l
~~~

Ví dụ kết quả:

~~~text
18420 app.jar
19215 org.example.Worker
~~~

Trong ví dụ, PID của app.jar là 18420. Hãy xác định đúng tiến trình trước khi gửi lệnh. Không dùng PID cũ đã được lưu từ lần chạy trước vì hệ điều hành có thể tái sử dụng PID.

### Bước 2: Kiểm tra command có sẵn

Có thể yêu cầu JVM liệt kê diagnostic command:

~~~bash
jcmd 18420 help
~~~

Nếu JVM có đăng ký JDK.checkpoint, xem phần trợ giúp riêng:

~~~bash
jcmd 18420 help JDK.checkpoint
~~~

Lệnh trợ giúp giúp xác nhận command được runtime hỗ trợ và hiển thị cú pháp hoặc tham số nếu bản JDK có cung cấp. Tên command và các tùy chọn có thể phụ thuộc bản phân phối CRaC.

Nếu JDK.checkpoint không xuất hiện, hãy kiểm tra lại bản JDK đang chạy, công cụ jcmd đang dùng và cấu hình CRaC. Không nên giả định rằng một JVM Java thông thường sẽ có command này.

### Bước 3: Gửi yêu cầu checkpoint

Khi đã xác định đúng PID và xác nhận command có sẵn, gửi:

~~~bash
jcmd 18420 JDK.checkpoint
~~~

jcmd gửi yêu cầu đến JVM đích. JVM CRaC điều phối quá trình chuẩn bị checkpoint, bao gồm việc gọi các resource callback đã đăng ký. Khi thao tác hoàn tất, ảnh checkpoint được tạo tại vị trí cấu hình của runtime.

Với lệnh được gọi từ bên ngoài, tiến trình gốc thường kết thúc sau khi checkpoint thành công; việc sử dụng ảnh để chạy lại tiến trình được thực hiện ở bước restore. Hãy kiểm tra kết quả lệnh, log của JVM và thư mục checkpoint để xác nhận thao tác thực tế. Thông báo trả về của jcmd có thể khác nhau giữa các bản JDK.

Không gửi lệnh đến tiến trình đang phục vụ giao dịch quan trọng nếu ứng dụng chưa có cơ chế drain hoặc chuẩn bị checkpoint phù hợp. Resource callback có thể đóng kết nối và dọn tài nguyên, nhưng không tự hiểu toàn bộ quy tắc nghiệp vụ của ứng dụng.

## 4. Yêu cầu checkpoint từ mã Java

Trong một số tình huống, ứng dụng cần tự quyết định thời điểm checkpoint. Ví dụ, ứng dụng chỉ nên checkpoint sau khi hoàn tất khởi tạo, khi không có yêu cầu đang xử lý hoặc sau khi chuyển sang trạng thái bảo trì.

CRaC cung cấp API trong package org.crac. Phương thức Core.checkpointRestore() cho phép mã Java yêu cầu chu kỳ checkpoint–restore:

~~~java
import org.crac.Core;

public final class CheckpointCoordinator {

    public void checkpointAtSafePoint() throws Exception {
        // Ứng dụng đã dừng nhận việc mới và xử lý xong công việc đang chạy.
        Core.checkpointRestore();

        // Khi tiến trình được restore thành công,
        // luồng thực thi tiếp tục từ vị trí sau lời gọi này.
        resumeApplication();
    }

    private void resumeApplication() {
        // Mở lại worker hoặc cho phép nhận yêu cầu mới.
    }
}
~~~

Lời gọi này thuộc API CRaC của runtime hỗ trợ. Ứng dụng cần có dependency API tương thích với bản JDK đang triển khai và chạy trên môi trường có khả năng checkpoint/restore.

Điểm quan trọng là lời gọi checkpointRestore() biểu diễn một chu kỳ checkpoint–restore từ góc nhìn mã ứng dụng. Khi tiến trình được restore, luồng thực thi tiếp tục từ vị trí sau lời gọi. Nếu checkpoint hoặc restore thất bại, lỗi được báo về ứng dụng thông qua exception của API hoặc lỗi runtime liên quan; ứng dụng cần có chính sách xử lý phù hợp.

Không gọi API ở một vị trí tùy ý chỉ vì muốn lưu trạng thái. Nên đặt lời gọi tại một điểm mà ứng dụng có thể bảo đảm công việc đang xử lý đã được hoàn tất hoặc tạm dừng an toàn.

### Phân biệt JDK.checkpoint và Core.checkpointRestore()

| Tiêu chí | jcmd với JDK.checkpoint | Core.checkpointRestore() |
|---|---|---|
| Nơi phát sinh yêu cầu | Bên ngoài JVM | Bên trong mã Java |
| Người hoặc thành phần kích hoạt | Người vận hành, script hoặc công cụ quản trị | Logic của ứng dụng |
| Đối tượng nhận yêu cầu | JVM được chỉ định bằng PID | JVM đang thực thi lời gọi |
| Mục đích | Ra lệnh checkpoint cho tiến trình đang chạy | Chủ động điều phối chu kỳ checkpoint–restore từ ứng dụng |
| Vị trí tiếp tục thực thi | Tiến trình được khởi chạy lại từ checkpoint theo cách restore của runtime | Sau lời gọi API khi tiến trình được restore |
| Chuẩn bị resource | JVM gọi callback CRaC đã đăng ký | JVM gọi callback CRaC đã đăng ký |

JDK.checkpoint là tên diagnostic command được gửi qua jcmd, không phải một phương thức Java công khai có dạng JDK.checkpoint(). Khi viết mã ứng dụng, dùng API CRaC như Core.checkpointRestore() theo tài liệu của runtime.

## 5. Chuẩn bị resource trước checkpoint

Một yêu cầu checkpoint chỉ là tín hiệu bắt đầu quy trình. Ứng dụng cần đăng ký resource để đóng, giải phóng hoặc lưu trạng thái của tài nguyên bên ngoài trước khi ảnh tiến trình được tạo và khôi phục lại chúng sau restore.

CRaC định nghĩa interface Resource với hai callback chính:

- beforeCheckpoint(): chạy trước khi tiến trình được checkpoint. Dùng để dừng nhận việc, hoàn tất tác vụ đang chạy và giải phóng tài nguyên cần tạo lại.
- afterRestore(): chạy sau khi tiến trình được khôi phục. Dùng để tạo lại kết nối, mở lại tài nguyên và tiếp tục dịch vụ.

Ví dụ một resource quản lý kết nối đến hệ thống bên ngoài:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    private RemoteClient client;

    public RemoteClientResource() {
        client = createClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingRequests();
        waitForInFlightRequests();
        client.close();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
        resumeAcceptingRequests();
    }

    private RemoteClient createClient() {
        return new RemoteClient();
    }

    private void stopAcceptingRequests() {
        // Chuyển ứng dụng sang trạng thái tạm dừng.
    }

    private void waitForInFlightRequests() throws Exception {
        // Chờ các request đang xử lý kết thúc với timeout.
    }

    private void resumeAcceptingRequests() {
        // Mở lại khả năng tiếp nhận request.
    }
}
~~~

RemoteClient, cách tạo client và các phương thức điều phối trong ví dụ là phần minh họa, cần thay bằng lớp thực tế. Resource được đăng ký với global context để JVM biết cần gọi callback trong chu kỳ CRaC.

### Những việc thường cần thực hiện trong beforeCheckpoint()

Tùy loại ứng dụng, callback trước checkpoint có thể cần:

1. Ngừng nhận request hoặc tác vụ mới.
2. Chờ request đang chạy hoàn tất hoặc hủy chúng theo chính sách ứng dụng.
3. Flush buffer và hoàn tất việc ghi dữ liệu cần thiết.
4. Commit hoặc rollback transaction đang mở.
5. Đóng kết nối mạng, connection pool hoặc client có trạng thái phiên không thể tái sử dụng sau restore.
6. Dừng lịch chạy định kỳ nếu lịch đó cần được khởi tạo lại.
7. Giải phóng file handle, native handle hoặc tài nguyên phụ thuộc môi trường.

Không nên chờ vô hạn trong callback. Một dịch vụ bên ngoài không phản hồi có thể làm checkpoint bị treo. Dùng timeout, log rõ tài nguyên đang chờ và quyết định có hủy checkpoint hay báo lỗi khi không thể đưa ứng dụng về trạng thái an toàn.

### Những việc thường cần thực hiện trong afterRestore()

Sau khi restore, ứng dụng cần kiểm tra hoặc tạo lại các tài nguyên có vòng đời gắn với hệ điều hành hoặc dịch vụ bên ngoài:

- Tạo kết nối mạng mới.
- Khởi tạo lại client và pool kết nối.
- Đọc lại thông tin endpoint hoặc credential nếu chúng có thể thay đổi.
- Khởi động lại worker và tác vụ định kỳ.
- Kiểm tra trạng thái dịch vụ phụ thuộc trước khi mở lại lưu lượng.

Không nên mặc định socket, kết nối database hoặc phiên xác thực được lưu trong bộ nhớ sẽ luôn hợp lệ sau restore. Cần tuân theo hướng dẫn của thư viện và dịch vụ tương ứng.

Nếu callback của một resource thất bại, checkpoint hoặc restore có thể không hoàn tất như mong muốn. Hãy ghi log đầy đủ, giải phóng tài nguyên theo khả năng và xác định rõ ứng dụng có thể tiếp tục chạy hay cần dừng.

## 6. Quy trình mẫu từ khởi chạy đến restore

Ví dụ dưới đây mô tả cách cấu hình thư mục checkpoint và gửi yêu cầu từ jcmd. Các tùy chọn CRaC có thể khác theo nhà cung cấp JDK, nên cần đối chiếu với bản runtime thực tế.

### Khởi chạy ứng dụng

Chuẩn bị thư mục và quyền truy cập:

~~~bash
mkdir -p /var/lib/myapp/checkpoint
~~~

Khởi chạy JVM với nơi lưu checkpoint:

~~~bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint \
  -jar app.jar
~~~

Ứng dụng hoàn tất khởi động và đăng ký các Resource cần thiết. Sau khi xác nhận ứng dụng đang ở trạng thái có thể checkpoint, tìm PID:

~~~bash
jcmd -l
~~~

### Gửi lệnh checkpoint

Giả sử PID là 18420:

~~~bash
jcmd 18420 help JDK.checkpoint
jcmd 18420 JDK.checkpoint
~~~

Sau khi lệnh chạy, kiểm tra log và thư mục đã cấu hình. Chỉ coi checkpoint sẵn sàng khi runtime báo thành công và ảnh checkpoint được tạo đầy đủ theo định dạng của bản JDK đó. Không sao chép một thư mục checkpoint đang được ghi dở.

### Restore từ checkpoint

Với các bản JDK CRaC hỗ trợ tùy chọn này, có thể khởi chạy tiến trình từ ảnh đã lưu bằng:

~~~bash
java \
  -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoint
~~~

Restore thường yêu cầu môi trường tương thích với môi trường tạo checkpoint, bao gồm bản JDK, kiến trúc, hệ điều hành, thư viện native và các đường dẫn phụ thuộc. Kiểm tra hướng dẫn của nhà cung cấp để biết yêu cầu cụ thể.

Nếu dùng Core.checkpointRestore() trong mã Java, ứng dụng đi qua chu kỳ checkpoint–restore theo API; khi restore thành công, luồng thực thi tiếp tục sau lời gọi. Cách khởi chạy hoặc quản lý ảnh checkpoint vẫn phụ thuộc runtime và môi trường triển khai.

## 7. Lỗi thường gặp khi yêu cầu checkpoint

### Không tìm thấy JDK.checkpoint

**Biểu hiện:** jcmd báo command không tồn tại hoặc không liệt kê JDK.checkpoint trong trợ giúp.

Nguyên nhân có thể là:

- JVM đang chạy không phải bản JDK có hỗ trợ CRaC.
- Công cụ jcmd đang dùng không tương thích với JVM mục tiêu.
- PID trỏ đến một tiến trình khác.
- Bản phân phối hoặc cấu hình runtime không cung cấp diagnostic command này.

Cách xử lý: xác nhận java -version, jcmd -l, PID, đường dẫn đến jcmd và tài liệu của bản JDK CRaC.

### Không attach được vào tiến trình

**Biểu hiện:** jcmd không kết nối được với PID hoặc báo lỗi quyền.

Kiểm tra:

- Tiến trình còn tồn tại và PID chính xác.
- jcmd chạy dưới tài khoản có quyền attach phù hợp.
- Lệnh chạy trên cùng máy hoặc đúng môi trường container.
- JVM có cho phép attach theo cấu hình hiện tại hay không.

Không nên tùy tiện chạy bằng quyền cao hơn nếu chưa hiểu mô hình quyền của môi trường triển khai.

### Không ghi được checkpoint

**Biểu hiện:** command thất bại, log báo không thể tạo ảnh hoặc không có checkpoint image hợp lệ.

Kiểm tra:

- Đường dẫn CRaCCheckpointTo đã cấu hình đúng khi khởi chạy JVM.
- Thư mục tồn tại và tài khoản JVM có quyền ghi.
- Ổ đĩa còn đủ dung lượng.
- Filesystem và môi trường chạy đáp ứng yêu cầu của runtime.
- CRIU, kernel và quyền hệ thống đã được thiết lập theo tài liệu JDK đang dùng.

Không dùng một thư mục checkpoint cũ hoặc đang ghi dở để restore. Nếu thao tác thất bại, cần xác định ảnh có được tạo hoàn chỉnh hay không trước khi thử lại.

### Callback beforeCheckpoint() bị treo hoặc ném exception

**Biểu hiện:** checkpoint chờ lâu, bị hủy hoặc log ghi nhận lỗi resource.

Nguyên nhân thường gặp là callback đang chờ một request chưa kết thúc, kết nối bên ngoài không phản hồi hoặc lock bị giữ bởi thread khác.

Cách xử lý:

- Ghi log tên resource và bước đang thực hiện.
- Đặt timeout cho thao tác chờ.
- Bảo đảm worker có thể nhận tín hiệu dừng.
- Tránh giữ lock trong khi gọi dịch vụ bên ngoài.
- Chỉ cho checkpoint tiếp tục khi trạng thái ứng dụng đáp ứng điều kiện an toàn.

### Restore thất bại hoặc ứng dụng không sẵn sàng

**Biểu hiện:** runtime không khôi phục được ảnh hoặc ứng dụng lỗi trong afterRestore().

Kiểm tra tính tương thích giữa môi trường checkpoint và restore, quyền truy cập tài nguyên, endpoint, credential, cấu hình và thư viện native. Đọc log của runtime cùng exception trong callback để xác định resource gây lỗi.

Nếu một kết nối không thể tạo lại, ứng dụng cần có chính sách retry hoặc dừng có kiểm soát. Không mở lại lưu lượng trước khi các dependency bắt buộc đã sẵn sàng.

## 8. Nguyên tắc vận hành an toàn

- Dùng đúng JDK có hỗ trợ CRaC và xác nhận command JDK.checkpoint tồn tại trước khi vận hành.
- Xác định chính xác PID và dùng jcmd có quyền attach phù hợp.
- Cấu hình đường dẫn checkpoint khi khởi chạy JVM và kiểm tra dung lượng, quyền ghi.
- Xem jcmd JDK.checkpoint là yêu cầu từ bên ngoài; dùng Core.checkpointRestore() khi ứng dụng cần chủ động điều phối chu kỳ.
- Đăng ký Resource cho kết nối và tài nguyên cần đóng trước checkpoint, mở lại sau restore.
- Dừng nhận công việc mới và chờ công việc đang chạy đạt trạng thái an toàn.
- Đặt timeout cho callback, tránh chờ vô hạn hoặc giữ lock trong thao tác I/O.
- Kiểm tra log và ảnh checkpoint hoàn chỉnh trước khi triển khai restore.
- Restore trong môi trường tương thích với môi trường đã tạo checkpoint.
- Bảo vệ thư mục checkpoint vì ảnh tiến trình có thể chứa dữ liệu nhạy cảm trong bộ nhớ.

Khi phân biệt được lệnh jcmd JDK.checkpoint với API Core.checkpointRestore(), người vận hành có thể chọn đúng điểm kích hoạt. jcmd phù hợp cho thao tác quản trị một JVM đang chạy; API phù hợp khi ứng dụng cần kiểm soát thời điểm checkpoint theo trạng thái nghiệp vụ. Dù dùng cách nào, việc đăng ký resource và chuẩn bị ứng dụng trước checkpoint vẫn là phần quyết định độ tin cậy của chu kỳ restore.
