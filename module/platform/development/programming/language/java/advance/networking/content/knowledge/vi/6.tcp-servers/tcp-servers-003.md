# Backlog và giới hạn hàng đợi kết nối TCP phụ thuộc hệ điều hành

Khi viết **máy chủ TCP** trong Java, chúng ta thường thấy tham số **backlog** ở **ServerSocket** hoặc **ServerSocketChannel**. Tên gọi gợi ý đây là số kết nối được xếp hàng chờ, nhưng giá trị truyền từ Java **không phải cam kết** hệ điều hành sẽ giữ chính xác từng ấy kết nối. Backlog là **yêu cầu cấu hình hàng đợi của socket đang listen**; hệ điều hành, phiên bản kernel, giới hạn hệ thống, trạng thái TCP handshake và tốc độ ứng dụng gọi **accept()** quyết định hành vi thực tế.

Vấn đề thường xuất hiện khi có một đợt truy cập đồng thời: client có thể hoàn thành hoặc gần hoàn thành TCP handshake trong lúc server chưa kịp nhận các kết nối khỏi hàng đợi; một số lần **connect()** có thể chậm, timeout hoặc thất bại. Tăng backlog đôi khi giúp hấp thụ một đợt bùng nổ ngắn, nhưng **không tăng được tốc độ xử lý lâu dài** nếu accept loop, worker hoặc tài nguyên hệ thống đang quá tải.

Bài học này giúp bạn phân biệt hàng đợi handshake với hàng đợi chờ accept, hiểu đúng Java API, mô hình phổ biến trên Linux và sự khác biệt giữa các hệ điều hành, tự chạy ví dụ Java 17, quan sát số liệu thực và chọn phương án vận hành an toàn.

## 1. Backlog thuộc giai đoạn nào của vòng đời kết nối?

Một TCP server thường đi qua các bước:

1. **bind** địa chỉ IP/cổng của listener.
2. **listen** để kernel nhận các kết nối đến và duy trì trạng thái/hàng đợi cần thiết.
3. **accept** để ứng dụng lấy một socket kết nối đã sẵn sàng từ kernel.
4. **read/write** để xử lý byte stream trên socket được accept.
5. **close** khi giao dịch/kết nối kết thúc.

~~~text
   TCP client                     TCP kernel server                  Java server
      |                                  |                                |
      | ------ SYN ---------------------> |                                |
      | <----- SYN-ACK ------------------ |                                |
      | ------ ACK ---------------------> |                                |
      |                          kết nối đủ điều kiện                  |
      |                          vào hàng đợi accept                  |
      |                                  | --- accept() ---------------> |
      |                                  | <-- Socket đã accept -------- |
      | <-------------------- dữ liệu ứng dụng qua socket -------------->|
~~~

Sơ đồ là mô hình giải thích cơ bản; đường đi chính xác còn phụ thuộc kernel, retransmission, TCP Fast Open, SYN cookies và các trường hợp lỗi. **Java ServerSocket.accept() không tự thực hiện mọi lần bắt tay TCP**: kernel đảm nhiệm phần mạng, rồi trả một socket đã sẵn sàng cho ứng dụng khi accept thành công.

Điểm quan trọng là **client connect thành công không có nghĩa Java đã accept connection ấy hoặc đã xử lý request**. Hệ điều hành có thể hoàn thành handshake và giữ kết nối trong hàng đợi chờ ứng dụng gọi accept. Thậm chí thời điểm hai đầu coi kết nối hoàn thành có thể khác nhau trong tình huống hàng đợi server bị áp lực.

### Backlog không phải những thứ sau

- **Không phải số kết nối TCP tối đa được phép sống**: sau accept, các kết nối có thể tiếp tục tồn tại trong nhiều giây/phút; giới hạn còn do file descriptors, bộ nhớ, cấu hình ứng dụng và tải.
- **Không phải giới hạn thread**: ServerSocket và worker pool là hai lớp khác nhau; backlog không tạo thread mới, không quyết định kích thước ExecutorService.
- **Không phải độ dài hàng đợi request nghiệp vụ**: một socket đã accept có thể mang nhiều request; queue trong ExecutorService, message broker hoặc database là câu chuyện khác.
- **Không phải kích thước receive/send buffer**: SO_RCVBUF, SO_SNDBUF giữ dữ liệu của socket, khác với số kết nối pending.
- **Không phải số client chắc chắn kết nối được trước khi bị từ chối**: kernel có thể áp giới hạn, thay đổi cách xếp hàng, retry, hoặc có trạng thái chưa phản ánh trong hàng đợi Java.

## 2. Hai loại hàng đợi thường gặp trên TCP Linux

Khi nói đến backlog trong thực tế, cần tách **trạng thái handshake chưa hoàn tất** khỏi **kết nối đã established nhưng chưa được accept**.

<escape>
</escape>

~~~text
Client gửi SYN
      |
      v
 [Trạng thái request/chưa hoàn tất handshake]
 [SYN queue hoặc cơ chế tương đương]
      |
      | Handshake hoàn tất theo quy tắc kernel
      v
 [Accept queue: kết nối hoàn tất nhưng chờ app]
      |
      | ServerSocket.accept()
      v
 [Socket đã accept: ứng dụng xử lý bằng thread/event loop]
~~~

**SYN queue / hàng đợi bắt tay chưa hoàn tất.** Trong mô hình Linux truyền thống, kernel theo dõi các request đang ở giai đoạn bắt tay TCP. Số lượng và chính sách giới hạn liên quan tới **net.ipv4.tcp_max_syn_backlog**. Khi bật SYN cookies và kích hoạt đường đi tương ứng, kernel có thể tránh lưu trạng thái per-SYN theo cách thông thường; không được vì vậy suy rằng toàn bộ server có khả năng xử lý vô hạn.

**Accept queue / hàng đợi kết nối hoàn tất chờ accept.** Trên Linux từ 2.2, tham số **backlog** của listen TCP chủ yếu xác định độ dài hàng đợi **kết nối đã thiết lập hoàn chỉnh đang chờ ứng dụng accept**. Linux giới hạn yêu cầu ấy bởi **net.core.somaxconn**. Nếu ứng dụng muốn backlog 10.000 nhưng somaxconn đang là 4.096, kernel có thể âm thầm giới hạn yêu cầu xuống mức đó theo tài liệu listen(2). Giá trị cụ thể **phải đọc ở máy đang chạy**, không đoán theo bản phân phối.

**Chú ý về số liệu:** “SYN queue” và “accept queue” là mô hình hữu ích để hiểu Linux TCP, không phải tiêu chuẩn API Java bảo đảm hai hàng đợi hữu hình với cùng cấu trúc trên mọi OS. Kernel, phiên bản và các tối ưu mạng có thể thay đổi việc quản lý request, ACK, retransmission và giới hạn thực tế.

| Khía cạnh | Kết nối chưa hoàn tất handshake | Kết nối hoàn tất nhưng chờ accept |
|---|---|---|
| Bước TCP | Đang xử lý bắt tay SYN/SYN-ACK/ACK | Đã đủ điều kiện trở thành socket ứng dụng |
| Mối quan tâm | Tài nguyên trước khi kết nối hoàn chỉnh, SYN flood, retransmission | Ứng dụng có lấy kết nối ra khỏi kernel kịp không? |
| Linux thường liên quan | **tcp_max_syn_backlog**, **tcp_syncookies** và các chính sách kernel | Giá trị **listen(backlog)** sau giới hạn **somaxconn** |
| Java thấy trực tiếp qua ServerSocket? | Không có API portable đọc số SYN đang chờ | Không có API portable lấy độ dài queue thực hoặc số pending |
| Quá tải | Có thể retry/drop hoặc dùng cơ chế chống SYN flood | Có thể khiến bắt tay bị kéo dài, drop/retry, timeout hoặc lỗi kết nối; không có kết quả đồng nhất trên mọi hệ |

### Điều gì xảy ra khi accept queue đầy?

Không có đáp án duy nhất là “kết nối thứ B+1 luôn bị Connection refused”. Trên Linux và các OS khác, cách xử lý còn tùy giai đoạn handshake, TCP option, retransmission, kernel policy và cấu hình. Một số client có thể thấy **connect() chậm**, **SocketTimeoutException**, **ConnectException** hoặc thậm chí tưởng đã kết nối trong khi ứng dụng server chưa thể xử lý. Những quan sát ấy không đo chính xác chiều dài backlog nếu đứng riêng lẻ.

**Backlog là lớp đệm cho các lần accept**, không phải phép bảo đảm độ trễ hay năng lực xử lý request sau khi accept.

## 3. Các API Java khai báo backlog như thế nào?

### 3.1. java.net.ServerSocket

Java 17 cung cấp những cách thường dùng:

~~~java
// Một server socket đã bind với backlog yêu cầu:
ServerSocket server = new ServerSocket(port, backlog, bindAddress);

// Hoặc tạo chưa bind rồi bind có backlog:
ServerSocket server2 = new ServerSocket();
server2.bind(new InetSocketAddress(bindAddress, port), backlog);
~~~

**Đây là đoạn API minh họa**, giả sử đã có import và biến port/backlog/bindAddress; khi dùng thật phải đóng listener bằng try-with-resources và xử lý IOException.

- **port = 0**: yêu cầu hệ điều hành cấp cổng động; đọc cổng thực bằng **getLocalPort()**.
- **backlog > 0**: giá trị đề nghị. Chính xác bao nhiêu pending connection, có bị cap hoặc bỏ qua hay không là **implementation-specific**.
- **backlog <= 0**: Java dùng **giá trị mặc định phụ thuộc implementation**; không nên hiểu “0 nghĩa là không có hàng đợi”.
- **new ServerSocket(port)** theo Java 17 API yêu cầu một mức mặc định 50 cho queue, nhưng **không có bảo đảm hệ điều hành thực thi đúng 50**. Việc hệ thống dùng backlog hiệu quả nào vẫn do implementation và OS.
- **bind(...)** cấu hình listener một lần. Với ServerSocket đã bind, không thể chỉ gọi bind lại để thay backlog; cần quản lý vòng đời listener/cấu hình triển khai phù hợp.

Tài liệu JDK nói rõ backlog là **requested maximum number of pending connections** và hệ điều hành có thể đặt giới hạn hoặc bỏ qua tham số. Không suy diễn công thức backlog Java = số client đồng thời.

### 3.2. java.nio.channels.ServerSocketChannel

Với Java NIO, bạn truyền backlog ngay khi bind:

~~~java
try (ServerSocketChannel channel = ServerSocketChannel.open()) {
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0), 128);
    // accept() hoặc đăng ký OP_ACCEPT với Selector theo mô hình I/O.
}
~~~

Đoạn minh họa này có các tên kiểu đã được import ở ví dụ Java tương ứng; nó chỉ cho thấy overload **bind(SocketAddress, int)**. **ServerSocketChannel.bind(endpoint)** không có tham số backlog tương đương với gọi overload cùng endpoint và backlog = 0 theo Java 17, tức để implementation chọn mặc định. ServerSocketChannel có thể dùng ở blocking hoặc non-blocking mode; đổi mode không làm backlog trở thành hạn mức cho mọi kết nối đang mở.

**AsynchronousServerSocketChannel.bind(endpoint, backlog)** cũng có tham số này với semantics phụ thuộc implementation. Đừng nhầm “async accept” làm OS bỏ qua listen queue: kernel vẫn phải xử lý và xếp hàng yêu cầu kết nối tới listener theo cơ chế của mình.

### 3.3. Không có “getBacklog()” portable

Java ServerSocket không đưa ra API tiêu chuẩn để hỏi “kernel đang thực thi bao nhiêu backlog?” hoặc “đã chiếm bao nhiêu slot?”. Nếu muốn biết **giới hạn hiệu quả** và **độ đầy hàng đợi** phải dùng công cụ/counter của chính hệ điều hành và đo trên host/network namespace đúng nơi tiến trình chạy.

## 4. Ví dụ Java 17 chạy được: yêu cầu backlog, nhận một connection

Chương trình đầu tiên có nhiệm vụ tách rõ **backlog được yêu cầu lúc bind** khỏi **việc accept một kết nối**. Nó chạy hoàn toàn trên loopback, dùng port 0 tránh trùng cổng, tạo một worker thread cho accept và một client trong cùng JVM. Đầu ra cố định; ví dụ không hề khẳng định kiểm thử được số slot thực của OS.

Tệp **BacklogBasicsDemo.java**:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BacklogBasicsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        int requestedBacklog = 8;

        try (ServerSocket listener =
                     new ServerSocket(0, requestedBacklog, loopback)) {
            listener.setSoTimeout(3_000);

            ExecutorService worker =
                    Executors.newSingleThreadExecutor();
            try {
                Future<Integer> received = worker.submit(() -> {
                    try (Socket accepted = listener.accept()) {
                        return accepted.getInputStream().read();
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.getOutputStream().write(65); // Ký tự ASCII A.
                    client.shutdownOutput();
                }

                System.out.println(
                        "Requested backlog: " + requestedBacklog);
                System.out.println(
                        "Accepted byte: "
                                + received.get(3, TimeUnit.SECONDS));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy (Java 17+):

~~~bash
javac -encoding UTF-8 BacklogBasicsDemo.java
java BacklogBasicsDemo
~~~

Đầu ra của lần chạy thành công:

~~~text
Requested backlog: 8
Accepted byte: 65
~~~

Trong ví dụ:

1. **new ServerSocket(0, 8, loopback)** yêu cầu backlog 8 và bind trên loopback.
2. Worker block ở **accept()** để nhận một connection.
3. Client hoàn thành connect rồi ghi một byte **65**.
4. Khi accept trả về, **accepted** là Socket **mới** cho kết nối ấy; socket listener vẫn đang ở trạng thái listen.
5. Read trả về byte 65 và Future chuyển kết quả sang main. Lệnh **shutdownOutput()** của client báo hết chiều gửi, nhưng không đóng listener.

**Điều ví dụ không chứng minh:** kernel đã cấp chính xác tám slot; tám client đồng thời là giới hạn; accept() chạy trong ExecutorService thì backlog có giá trị là tám thread. Backlog vẫn là yêu cầu tới OS khi bind.

## 5. Ví dụ thí nghiệm: cố ý không accept để quan sát quá tải

Để thấy ảnh hưởng của một listener không gọi accept, ta có thể giữ socket server **đang listen** nhưng không bao giờ gọi **accept()**, lần lượt thử nhiều client loopback và giữ các Socket đã connect thành công. Kết quả phụ thuộc OS, kernel, số lần retransmission và timeout. Vì vậy chương trình **không in dự đoán cố định số kết nối thành công**.

**Lưu ý:** đây là thí nghiệm giáo dục cục bộ; không dùng để đo benchmark năng lực production. Với loopback và timeout ngắn, sự khác nhau giữa các máy là điều bình thường.

Tệp **BacklogProbeDemo.java**:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.List;

public class BacklogProbeDemo {
    public static void main(String[] args) throws Exception {
        final int attempts = 12;
        final int requestedBacklog = 2;
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(
                0, requestedBacklog, loopback)) {

            List<Socket> connectedSockets = new ArrayList<>();
            int timedOut = 0;
            int otherErrors = 0;

            try {
                // Không gọi listener.accept() để các connection
                // không được ứng dụng rút khỏi hàng đợi accept.
                for (int i = 0; i < attempts; i++) {
                    Socket client = new Socket();
                    try {
                        client.connect(new InetSocketAddress(
                                loopback, listener.getLocalPort()), 250);
                        connectedSockets.add(client);
                    } catch (SocketTimeoutException ex) {
                        timedOut++;
                        client.close();
                    } catch (IOException ex) {
                        otherErrors++;
                        client.close();
                    }
                }

                System.out.println("Attempts: " + attempts);
                System.out.println(
                        "Connected: " + connectedSockets.size());
                System.out.println("Timed out: " + timedOut);
                System.out.println("Other errors: " + otherErrors);
                System.out.println(
                        "Total accounted: "
                                + (connectedSockets.size()
                                + timedOut + otherErrors));
            } finally {
                for (Socket socket : connectedSockets) {
                    socket.close();
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BacklogProbeDemo.java
java BacklogProbeDemo
~~~

**Hai dòng xác định nếu chương trình kết thúc bình thường**:

~~~text
Attempts: 12
Total accounted: 12
~~~

Ba dòng ở giữa (**Connected**, **Timed out**, **Other errors**) có số đo **thay đổi theo máy và lần chạy**; không nên sao chép một con số giả định làm “expected output”. Một số hệ thống có thể nhận hơn mức backlog được yêu cầu do cơ chế queue, hằng số kernel hoặc thời điểm handshakes; có hệ thống cho timeout, lỗi hoặc số lượng thành công khác. Nếu cả 12 lần connect thành công, đó **không chứng minh backlog đã bị bỏ qua một cách vô điều kiện**; nó chỉ là dữ liệu của thử nghiệm cụ thể.

Điều quan trọng nhất của thí nghiệm: server vẫn **listen** nhưng **không accept**; sự thiếu vắng accept cho phép các kết nối hoàn tất tích lại ở kernel cho tới khi chính sách OS tác động. Thử sửa thành một accept loop liên tục rồi chạy lại; cách xử lý/đo cần thay đổi để tránh socket bị đóng tức thì làm kết quả sai lệch.

## 6. Các giới hạn quan trọng trên Linux

Ở Linux hiện đại, chỉ riêng **backlog trong mã Java** chưa đủ để xác định sức chứa hàng đợi:

| Cấu hình/điểm đo | Vai trò | Điều không được hiểu nhầm |
|---|---|---|
| **listen(backlog)**, do Java truyền khi bind | Yêu cầu độ dài accept queue cho các connection đã thiết lập đang đợi app accept | Không tự đặt max connection đang hoạt động |
| **net.core.somaxconn** | Giới hạn trên đối với backlog của listener; yêu cầu cao hơn bị cap theo Linux listen(2) | Không phải độ dài SYN queue, cũng không bảo đảm hiệu năng |
| **net.ipv4.tcp_max_syn_backlog** | Giới hạn liên quan đến request TCP chưa hoàn thành bắt tay trong đường đi không dùng SYN cookies | Không phải số Socket Java chờ accept |
| **net.ipv4.tcp_syncookies** | Cơ chế bảo vệ khi áp lực SYN, có thể đổi cách kernel giữ trạng thái handshake | Không phải công tắc tăng hiệu năng ứng dụng hay bỏ giới hạn accept queue |
| **Số file descriptors / bộ nhớ socket** | Giới hạn tài nguyên của tiến trình và kernel | Backlog cao không cấp thêm FD/heap/thread |
| **Worker pool, executor queue, database** | Quyết định app xử lý socket đã accept nhanh tới đâu | Không được tính vào backlog kernel |

Theo **listen(2)**, từ Linux 2.2 backlog TCP mô tả queue của **kết nối đã được thiết lập chờ accept**, còn giới hạn incomplete requests thuộc **tcp_max_syn_backlog** (trong điều kiện áp dụng). Tài liệu man-pages nêu **somaxconn** có giá trị mặc định 4.096 từ Linux 5.4, trước đó thường 128; đây là **mặc định theo tài liệu**, **không phải bảo đảm cấu hình của máy đang chạy**. Distro, container và quản trị viên có thể dùng giá trị khác.

Có thể nghĩ đơn giản:

~~~text
backlog hiệu quả của accept queue
  <= backlog do ứng dụng yêu cầu
  <= hoặc bị giới hạn bởi somaxconn theo chính sách kernel
~~~

Đây là **cách hình dung giới hạn**, không phải công thức để tính số client chắc chắn connect được. Hành vi còn có tình huống off-by-one, retry, cấu trúc queue và cạnh tranh thời gian; không nên dùng “backlog B = chính xác B thành công, client thứ B+1 chắc chắn bị từ chối” làm invariant trong test.

### Quan sát cấu hình và hàng đợi trên máy Linux

Các lệnh dưới đây là **lệnh Linux để người học tự chạy trên môi trường của mình**, không phải đầu ra do Java in:

~~~bash
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
sysctl net.ipv4.tcp_syncookies
ss -lnt
nstat -az | grep -E 'ListenOverflows|ListenDrops|Syncookies'
~~~

Cách đọc:

- **sysctl** cho biết cấu hình hiện tại trong network namespace/kernel mà bạn đang quan sát; nếu chạy trong container, cần phân biệt namespace container và host. Một vài giá trị có thể được quản lý ở cấp node và không cho phép sửa từ container.
- Trên nhiều phiên bản Linux, **ss -lnt** cho listening TCP sockets; cột **Recv-Q** có thể cho biết số connection hoàn tất đang đợi accept, còn **Send-Q** phản ánh mức backlog chấp nhận của listener. Phải đối chiếu đúng phiên bản **iproute2** và kernel, không áp dụng cách diễn giải này cho mọi socket state và mọi hệ điều hành.
- Các bộ đếm **ListenOverflows**, **ListenDrops**, **Syncookies...** trong thống kê TCP (ví dụ qua **nstat**) là tín hiệu điều tra sự cố, nhưng tên counter, cơ chế cập nhật và khả năng hiển thị phụ thuộc kernel.
- Nên đo **mức sử dụng theo thời gian** và chênh lệch counter trước/sau bài thử, không chỉ chụp một con số tại một thời điểm. Counter hệ thống có thể cộng cho nhiều listener, nên không kết luận tất cả overflow thuộc ứng dụng của bạn.

**Đừng chạy lệnh tăng sysctl một cách mù quáng** trong môi trường production. Việc điều chỉnh kernel cần kết hợp phân tích nguồn giới hạn, tài nguyên và đặc thù bảo mật. Thay đổi cấu hình node/container có thể tác động nhiều dịch vụ.

## 7. Backlog và tốc độ accept: vì sao tăng queue không giải quyết overload lâu dài?

Giả sử có một đợt các client thiết lập TCP connection:

- **Tốc độ đến**: 200 kết nối mới/giây.
- **Tốc độ ứng dụng accept được**: 150 kết nối/giây.
- **Chênh lệch**: queue có xu hướng tăng 50 kết nối/giây khi các số đo giữ tương tự.

Nếu phần queue trống hữu dụng ban đầu khoảng **100 slot**, nó có thể bị lấp gần đầy sau khoảng **2 giây** trong một mô hình lý tưởng đơn giản. Thực tế phải đo: arrival không đều, handshake còn chờ, tốc độ accept thay đổi, kernel có thể cap/retry, và các connection có thể đóng.

~~~text
Kết nối đến (lambda) ---> [ ACCEPT QUEUE ] ---> accept() (mu)
                              |
                           backlog
          lambda > mu lâu dài => queue có xu hướng đầy
          lambda <= mu ổn định => queue có cơ hội được rút cạn
~~~

**Tăng backlog giúp hấp thụ burst tạm thời**, tức cho app thêm thời gian lấy connection khỏi queue. Nếu tốc độ đến liên tục vượt tốc độ accept, queue lớn cuối cùng vẫn đầy và chỉ có thể biến lỗi nhanh thành thời gian chờ dài hơn. Năng lực thực sự cần tăng bằng cải thiện accept loop, giảm công việc blocking tại luồng accept, scale instance đúng cách và quản lý tài nguyên downstream.

### Phân biệt các hàng đợi trong kiến trúc server

~~~text
Kernel SYN state -> Kernel accept queue -> Java accept()
                                        |
                                        v
                                 Thread pool queue
                                        |
                                        v
                             Parse/TLS/DB/Business logic
~~~

- **Accept queue** chứa những connection chưa được app accept.
- **ExecutorService queue** chứa những task đã được app tạo sau accept. Nó có thể đầy khi số worker quá nhỏ hoặc xử lý request quá chậm; đây là **hàng đợi khác**.
- **Socket receive buffer** chứa dữ liệu của một connection. Nó không phải backlog.
- **Connection pool** tới database cũng là tài nguyên khác; backlog lớn không tăng số kết nối tới DB hoặc thông lượng DB.

Một kiểu server chậm là gọi **accept()**, sau đó xử lý **đọc request + gọi DB + ghi response** ngay trong cùng luồng rồi mới accept tiếp. Dù mỗi xử lý tốn 500 ms, listener chỉ có thể accept khoảng hai connection/giây theo mô hình ấy, khiến queue nhanh đầy khi burst đến. Cách thiết kế thường là giữ accept loop nhẹ, giao socket đã accept cho worker với **số lượng hữu hạn** và áp dụng backpressure/admission control.

## 8. Thiết kế accept loop và overload control

Với server có lượng kết nối đáng kể:

1. **Đọc cấu hình backlog như một giá trị yêu cầu**, xác định giới hạn OS, sau đó benchmark cùng workload dự kiến.
2. **Không thực hiện tác vụ chậm trong accept loop**. Mỗi lần accept nên nhanh chóng chuyển Socket tới worker/event loop, hoặc đóng hợp lệ khi không thể nhận thêm tải.
3. **Giới hạn hàng đợi worker và số connection đang hoạt động**. Hàng đợi trong JVM vô hạn có thể làm heap tăng dù accept queue kernel không đầy.
4. **Dùng timeout và deadline thích hợp**. **ServerSocket.setSoTimeout(...)** áp dụng cho *lần chờ accept*; nó không thay đổi backlog, không tự timeout việc xử lý client đã accept. **Socket.connect(address, timeout)** giới hạn thời gian chờ connect phía client theo hợp đồng API; không tạo bảo đảm server đã accept hoặc xử lý.
5. **Theo dõi p95/p99 connect latency, accept rate, pending queue, worker saturation, FD, CPU, memory, TCP retransmissions và lỗi/timeouts**, đồng thời đối chiếu log tại LB/proxy.
6. **Thực hiện load test với kết nối dài/ngắn khác nhau**. Burst of new connections có thể làm đầy accept queue dù request throughput bình quân thấp; keep-alive giảm tần suất thiết lập connection, nhưng cần theo protocol và khả năng quản lý các kết nối đang rảnh.
7. **Ưu tiên đo và sửa nút thắt**: worker bị DB chặn, handshake TLS nặng, CPU parse, GC hoặc giới hạn FD đều không tự biến mất khi tăng backlog.

### Tại sao backlog 10.000 không có nghĩa 10.000 client đang hoạt động?

Sau khi **accept()** trả về Socket, kết nối không còn chờ trong accept queue. Một server có thể giữ nhiều nghìn Socket đã accept nếu tài nguyên và kiến trúc cho phép, ngay cả khi backlog yêu cầu nhỏ. Ngược lại, listener với backlog lớn vẫn có thể chỉ xử lý được vài request/giây nếu ứng dụng downstream chậm.

**Không dùng backlog để giới hạn người dùng đồng thời.** Hãy quản lý số active connections, session, request, hàng đợi xử lý và tài nguyên theo chính sách riêng.

### ServerSocketChannel, Selector và virtual threads có thay đổi backlog không?

**Không thay đổi bản chất listen queue của OS.** Blocking ServerSocket, NIO ServerSocketChannel với Selector và server dùng virtual threads (Java 21+) đều cần kernel tiếp nhận kết nối. Các mô hình này thay đổi cách ứng dụng accept, phân phối và xử lý Socket sau khi accept, từ đó có thể làm tốc độ rút queue tốt hơn. Nhưng tham số backlog của listener vẫn chịu luật OS; virtual threads không phải phép bỏ qua somaxconn.

## 9. Những lỗi quan sát và diễn giải thường gặp

| Hiện tượng | Khả năng liên quan | Cần kiểm tra thêm |
|---|---|---|
| connect latency tăng khi có burst | Listener/accept queue chậm, handshake retry, network/LB | ss, TCP counters, thời gian accept, network trace |
| connect timeout | Mạng, firewall, load balancer, listener queue, retransmission | Không kết luận ngay “backlog thiếu” |
| Connection refused | Không có listener phù hợp, reject bởi OS/firewall, lỗi routing/cấu hình hoặc điều kiện queue | Port/IP/namespace, listener tồn tại không, counters |
| accept() lâu mới trả về | Không có connection sẵn sàng, điều kiện mạng, timeout riêng của accept | Không mặc nhiên là queue quá nhỏ |
| Các request chậm sau connect thành công | Worker, database, TLS, CPU, app queue | Metrics application; backlog có thể hoàn toàn bình thường |
| Java OutOfMemoryError khi nhiều socket | Giới hạn heap/direct buffers, task queue, thread, object lifecycle | Không chữa bằng tăng backlog |
| Nhiều SYN_RECV | Handshake đang chờ, client/network/SYN flood hoặc load lớn | tcp_max_syn_backlog, syncookies, counters, network |
| ss Recv-Q tăng sát giới hạn | Nhiều completed connections đang chờ accept (trên Linux nơi cột có nghĩa này) | Tốc độ accept, CPU/GC, file descriptors, kernel version |

**Quan sát phải gắn đúng socket và đúng môi trường chạy.** Container, Kubernetes pod, reverse proxy hoặc load balancer có listener riêng của chúng; hàng đợi tại edge proxy không giống hàng đợi tại server Java backend. Nếu load test vào load balancer, connect() thành công ở client có thể chỉ chứng minh phía LB đã nhận connection.

**Tăng backlog không phải cách vá SYN flood.** SYN cookies và các cơ chế giảm thiểu tấn công là vấn đề bảo vệ lớp TCP riêng; backlog cho pending fully-established connections không thay thế chính sách rate limiting, firewall và bảo vệ tài nguyên ứng dụng.

## 10. Cách kiểm chứng trên Windows, BSD, macOS và Linux

**Java API là portable về chữ ký phương thức, nhưng semantics chi tiết của backlog không portable.**

- **Linux**: có hai khía cạnh thường được tách riêng là handshake request và accept queue; listen backlog chịu giới hạn somaxconn; có các sysctl và công cụ thống kê tương ứng.
- **BSD/macOS**: kernel có thể có cách quản lý, giới hạn và mối quan hệ backlog với handshake khác. Không lấy mô hình, counter hoặc giá trị Linux áp thẳng cho hệ khác.
- **Windows**: backlog được chuyển xuống tầng Winsock/implementation; giới hạn hiệu quả và hành vi khi overload phải theo API Windows và phiên bản hệ điều hành. Không dùng sysctl hoặc ss Linux để suy luận.
- **Container/VM**: image Java giống nhau vẫn có thể chạy trên kernel và namespace khác; một số giới hạn đặt ở host, proxy hoặc mạng ảo; phải đo trong môi trường triển khai cụ thể.

Khi so sánh giữa hai máy, phải ghi lại **JDK version**, **OS/kernel version**, **bind address**, **requested backlog**, cấu hình OS, có proxy/LB không, cách tạo tải, thời gian đo và trạng thái worker/server. Nếu thiếu những dữ liệu này, kết luận "backlog=128 nhanh hơn backlog=64" thường không có cơ sở.

## 11. Bài tập thực hành

### Bài tập 1 — Backlog API của Java

Chạy **BacklogBasicsDemo.java**, đổi requestedBacklog từ 8 sang 1 rồi 512. Xác minh **một** kết nối thành công trên loopback và giải thích vì sao cả ba kết quả như nhau không chứng minh kernel đã dùng đúng ba queue size đó.

### Bài tập 2 — Quan sát trong lúc server không accept

Chạy **BacklogProbeDemo.java** với backlog 1, 2, 16. Ghi lại Connected/Timed out/Other errors cho từng lần chạy. Lặp lại vài lượt và kiểm tra cấu hình OS. Vì sao tổng kết quả có thể biến động và không thể dùng một lần connect làm phép đo chính xác số slot queue?

### Bài tập 3 — Thêm accept loop

Thêm một worker liên tục accept rồi giữ Socket trong một collection có giới hạn; so sánh với phiên bản hoàn toàn không accept. Lưu ý đóng mọi Socket và dừng worker đúng cách. Giải thích việc rút connection khỏi accept queue khác với hoàn tất xử lý request.

### Bài tập 4 — Phân tích hai hàng đợi

Trên Linux, ghi lại **net.core.somaxconn**, **net.ipv4.tcp_max_syn_backlog**, **net.ipv4.tcp_syncookies** và quan sát **ss -lnt**. Phân loại số liệu nào liên quan đến incomplete handshake, số liệu nào liên quan completed connections đang đợi accept. Không sửa sysctl khi chỉ cần quan sát.

### Bài tập 5 — Thí nghiệm app xử lý chậm

Trong một server do bạn kiểm soát, so sánh hai kiến trúc: (A) xử lý yêu cầu chậm ngay sau accept trong một luồng; (B) accept nhanh và đẩy việc xử lý sang worker bounded. Dưới tải tăng dần, đo connect latency, accept rate, worker queue depth, memory và error rates. Vì sao chỉ tăng backlog không cứu được throughput khi downstream bị giới hạn?

## 12. Câu hỏi kiểm tra hiểu đúng

**1. Backlog có phải số lượng kết nối đang hoạt động tối đa không?** Không. Nó liên quan đến yêu cầu queue cho connection đang chờ ứng dụng accept, còn active connections đã được accept được quản lý và giới hạn bằng cơ chế khác.

**2. new ServerSocket(port, 10) bảo đảm kết nối thứ 11 bị từ chối chứ?** Không. Ngữ nghĩa và giới hạn cụ thể phụ thuộc implementation/OS, cộng với timing và trạng thái bắt tay.

**3. Backlog trong Linux hiện đại giới hạn SYN queue hay accept queue?** Theo tài liệu listen(2) từ Linux 2.2, backlog TCP chỉ queue của fully-established connections đang đợi accept; incomplete request chịu cơ chế khác, bao gồm tcp_max_syn_backlog và SYN cookies.

**4. Nếu Java yêu cầu backlog 10.000 còn somaxconn = 4.096 thì sao?** Trên Linux theo tài liệu listen(2), yêu cầu cao hơn giới hạn bị kernel cap xuống somaxconn; không thể kết luận số client connect thành công bằng chính xác 4.096 chỉ từ điều đó.

**5. connect() trả về thành công nghĩa server code đã chạy accept()?** Không. TCP handshake có thể hoàn thành trong kernel trước khi app lấy Socket khỏi queue; xử lý application càng chưa được bảo đảm.

**6. ServerSocket.setSoTimeout(1000) giúp backlog dài hơn?** Không. Nó giới hạn thời gian chờ của lời gọi accept blocking, không thay đổi số pending connections cho listener.

**7. Tăng backlog có chữa lỗi worker pool chậm không?** Không. Nó có thể đệm burst connection trong thời gian ngắn, nhưng không tăng CPU, DB throughput hay số worker khỏe mạnh.

**8. Có thể đo backlog thực qua ServerSocket.getBacklog() không?** Không có phương thức portable như vậy trên ServerSocket; cần công cụ OS và đo trên môi trường triển khai cụ thể.

## Tài liệu tham khảo trực tiếp

- **Java SE 17 — ServerSocket**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Java SE 17 — ServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- **Java SE 17 — AsynchronousServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- **Linux man-pages — listen(2)**: https://man7.org/linux/man-pages/man2/listen.2.html
- **Linux man-pages — tcp(7)**: https://man7.org/linux/man-pages/man7/tcp.7.html

**Ghi nhớ:** **backlog là yêu cầu giới hạn hàng đợi kết nối đang chờ accept ở listener, không phải giới hạn mọi kết nối đang hoạt động hay tốc độ xử lý request.** Hệ điều hành quyết định cách diễn giải và giới hạn hiệu quả; trên Linux còn có somaxconn và các chính sách SYN riêng. Thiết kế server đúng đòi hỏi accept đủ nhanh, worker có giới hạn, observability ở kernel lẫn ứng dụng, load test thực tế và xử lý overload có chủ đích.