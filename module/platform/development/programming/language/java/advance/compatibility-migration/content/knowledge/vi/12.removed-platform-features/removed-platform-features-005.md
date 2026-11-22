# RMI Activation và ảnh hưởng đến hệ thống dùng cơ chế kích hoạt cũ

Trong một số hệ thống Java lâu năm, đối tượng từ xa không được tạo ngay khi ứng dụng khởi động mà chỉ được khởi tạo khi một client thực sự gọi tới. Cơ chế này từng được Java RMI hỗ trợ qua **RMI Activation** và tiến trình **`rmid`**. Khi nâng JDK, đặc biệt từ Java 8 hoặc Java 11 lên Java 17 trở đi, những hệ thống dựa vào Activation có thể thất bại dù phần lớn mã Java RMI thông thường vẫn được hỗ trợ.

Điểm phân biệt quan trọng nhất: **RMI Activation đã bị loại bỏ, nhưng Java RMI nói chung không bị loại bỏ chỉ vì thay đổi này.** Các ứng dụng sử dụng `Remote`, `RemoteException`, `UnicastRemoteObject` và RMI registry có thể tiếp tục vận hành nếu mã nguồn, dependency, cấu hình và môi trường tương thích. Ngược lại, ứng dụng sử dụng `java.rmi.activation.*`, daemon `rmid` hoặc mô hình kích hoạt đối tượng theo yêu cầu phải được thiết kế lại phần vòng đời dịch vụ.

Bài học này giải thích kiến trúc Activation trước đây, mốc thay đổi qua các JDK, tác động lên build và runtime, các phương án thay thế, ví dụ RMI không dùng Activation và quy trình chuyển đổi an toàn trong **Java Advance Compatibility Migration**.

## 1. Ôn lại Java RMI thông thường

Java Remote Method Invocation (RMI) cho phép một chương trình Java gọi phương thức của đối tượng từ xa thông qua một remote interface. Một ứng dụng RMI điển hình có:

- **Remote interface:** khai báo các phương thức có thể gọi từ xa; thông thường interface mở rộng `java.rmi.Remote` và remote methods khai báo `RemoteException`.
- **Remote implementation:** đối tượng hiện thực nghiệp vụ.
- **Exported remote object:** đối tượng được export để RMI runtime nhận cuộc gọi từ xa; có thể dùng `UnicastRemoteObject`.
- **RMI registry:** nơi đăng ký tên và remote reference để client tra cứu bằng `Registry.lookup` hoặc API tương ứng.
- **Client:** lấy remote reference rồi gọi phương thức, xử lý lỗi mạng và lỗi nghiệp vụ.

Luồng đơn giản:

~~~text
Server process                            Client process
+-------------------------+               +--------------------------+
| Create service object   |               | Locate RMI registry      |
| Export remote object    |               | Lookup service name      |
| Bind to RMI registry    |<-- lookup ----| Receive remote reference |
| Wait for remote calls   |<-- invoke ----| Call remote method       |
| Execute business logic  |---- reply --->| Handle result/error      |
+-------------------------+               +--------------------------+
~~~

Trong mô hình này, **server process phải đang chạy và remote object phải được export** trước khi client gọi được. RMI registry không tự khởi động server nếu process đã dừng. Nó là dịch vụ đăng ký và tra cứu remote reference, không phải process supervisor.

RMI Activation từng bổ sung một cơ chế riêng để khởi tạo hoặc tái kích hoạt đối tượng khi được yêu cầu, thay vì để mỗi service luôn chạy sẵn.

## 2. RMI Activation được thiết kế để giải quyết vấn đề gì?

Trong một hệ thống lớn, một số remote object hiếm khi được gọi. Giữ tất cả server process hoạt động liên tục có thể tiêu tốn memory, thread, connection hoặc chi phí quản trị. RMI Activation từng cung cấp cách để một remote object có **activation descriptor** được đăng ký trong một activation system, rồi được kích hoạt khi một remote call yêu cầu đối tượng chưa hoạt động.

Mô hình khái niệm:

~~~text
                 Client
                   |
                   | Gọi remote object qua activatable reference
                   v
          +-------------------+
          | Activation system |
          |       rmid        |
          +-------------------+
                   |
                   | Tìm thông tin đăng ký
                   | Chọn/kích hoạt activation group
                   v
          +-------------------+
          | JVM/group process |
          |  Activated object |
          +-------------------+
                   |
                   | Object ready / remote reference
                   v
          +-------------------+
          | Remote invocation |
          +-------------------+
~~~

Về nguyên lý, Activation cho phép đăng ký mô tả đối tượng từ trước và để activation daemon hỗ trợ đưa implementation vào trạng thái sẵn sàng khi có yêu cầu. Trong hệ thống cũ, thông tin registration có thể được ghi vào log/database của activation daemon, phục vụ khôi phục trạng thái đăng ký qua các lần daemon chạy.

Điều quan trọng cần hiểu:

1. Đây là **cơ chế vòng đời đối tượng từ xa** của RMI, không phải chỉ là tên khác của RMI registry.
2. Nó có thể liên quan việc khởi động JVM/process activation group, nhưng không tương đương process supervisor hiện đại.
3. Cơ chế hoạt động phụ thuộc vào daemon `rmid`, API activation và cấu hình chạy phù hợp.
4. RMI Activation không tự bảo đảm dữ liệu nghiệp vụ được lưu bền vững; application vẫn phải quản lý state riêng.
5. Việc Activation từng hỗ trợ startup theo yêu cầu **không có nghĩa** có thể bỏ daemon và giữ nguyên remote reference khi nâng JDK.

## 3. Các thành phần legacy cần nhận diện

Những ứng dụng từng dùng Activation thường có các dấu hiệu sau:

| Thành phần hoặc symbol | Vai trò lịch sử | Cần xử lý khi nâng JDK mới |
|---|---|---|
| `java.rmi.activation.Activatable` | Hỗ trợ exported activatable remote objects | Chuyển sang lifecycle khác, thường là RMI thường hoặc giao thức khác |
| `ActivationID` | Nhận diện đối tượng trong activation system | Thay mô hình identity/lookup phù hợp |
| `ActivationDesc` | Mô tả cách kích hoạt một đối tượng | Di chuyển cấu hình khởi tạo sang service deployment/config |
| `ActivationGroup` | Quản lý nhóm đối tượng được kích hoạt | Thay bằng process/container/service lifecycle |
| `ActivationGroupDesc` | Mô tả thuộc tính nhóm hoạt động | Chuyển startup options, properties và policy |
| `ActivationSystem` | Interface quản lý đăng ký activation | Không thể chỉ dùng Registry thay thế từng phương thức |
| `Activator` / `ActivationMonitor` | Phối hợp kích hoạt và theo dõi trạng thái | Thiết kế lại cơ chế sẵn sàng và quan sát |
| `rmid` | Activation daemon ngoài ứng dụng | Không còn được cung cấp từ JDK 17 |
| Script khởi chạy `rmid` | Thường cấu hình port, log, policy, environment | Loại bỏ hoặc thay bằng supervisor khác |
| RMI registry/`rmiregistry` | Đăng ký/tra cứu remote reference | Là thành phần khác, không tự bị xóa theo Activation |

Một số hệ thống không import `java.rmi.activation` trực tiếp ở module nghiệp vụ nhưng vẫn phụ thuộc gián tiếp qua thư viện, utility JAR hoặc startup scripts. Vì vậy, cần kiểm tra cả source, bytecode, packaging và quy trình vận hành.

### 3.1. Activation system khác Registry

RMI registry trả lời câu hỏi **“tên dịch vụ này ánh xạ tới remote reference nào?”**. Activation system trả lời câu hỏi liên quan **“đối tượng được đăng ký này sẽ được kích hoạt như thế nào khi cần?”**.

Chỉ thay `ActivationSystem.registerObject(...)` bằng `Registry.rebind(...)` không tái tạo hành vi activation. Muốn giữ client gọi được, service phải chủ động tạo/export object và đăng ký remote reference vào registry; đồng thời một cơ chế khác phải giám sát process và tái khởi động khi cần.

### 3.2. Activation group khác process manager mới

Activation group của RMI gắn với đặc tả và cách tổ chức tiến trình/nhóm hoạt động của hệ Activation. Khi migration sang systemd, Windows Service, container orchestrator hoặc scheduler, không có khái niệm “activation group” tương đương tuyệt đối. Cần chuyển từng yêu cầu: startup arguments, credential, Java options, working directory, resources, restart policy và isolation boundary.

## 4. Mốc phiên bản: deprecate và remove không giống nhau

RMI Activation trải qua hai bước quan trọng trong lộ trình JDK hiện đại:

| Java release | Tình trạng RMI Activation | Ý nghĩa migration |
|---|---|---|
| Java 8 | Có API Activation và công cụ `rmid` | Ứng dụng legacy có thể dựa vào cơ chế kích hoạt cũ |
| Java 9–14 | Có JPMS và các thay đổi runtime; Activation vẫn là thành phần legacy | Nên rà soát trước khi lên Java mới |
| **Java 15** | **JEP 385: Deprecate RMI Activation for Removal** | API và tool bị đánh dấu dự kiến loại bỏ; chuẩn bị thay thế |
| Java 16 | Giai đoạn chuyển tiếp với deprecation for removal | Không nên phát triển mới phụ thuộc Activation |
| **Java 17** | **JEP 407: Remove RMI Activation** | API activation và daemon `rmid` bị loại bỏ khỏi JDK |
| Java 21 và các JDK mới hơn | Không nên kỳ vọng Java RMI Activation quay trở lại | Phải vận hành bằng thiết kế không phụ thuộc cơ chế đã loại bỏ |

Phân biệt ba khái niệm:

- **Deprecated:** API không được khuyến khích sử dụng nhưng vẫn có thể tồn tại.
- **Deprecated for removal:** API được đánh dấu có kế hoạch loại bỏ trong tương lai, cần ưu tiên chuyển đổi.
- **Removed:** API/tool không còn được cung cấp trong JDK tương ứng; mã phụ thuộc có thể không compile hoặc không chạy.

Một hệ thống vẫn khởi động được trên Java 11 không chứng minh nó tương thích Java 17. Nếu phụ thuộc Activation, đây là chênh lệch về **năng lực nền tảng** chứ không chỉ là cảnh báo compiler.

## 5. Java RMI thông thường vẫn là một cơ chế riêng

Điều bị loại bỏ là **RMI Activation**, không phải toàn bộ module `java.rmi`. Những khả năng RMI cơ bản vẫn có ý nghĩa trên Java hiện đại:

- `java.rmi.Remote` và `java.rmi.RemoteException`.
- `java.rmi.server.UnicastRemoteObject` để export remote object.
- `java.rmi.registry.Registry` và `LocateRegistry` để đăng ký/tra cứu.
- Remote invocation và RMI transport khi cấu hình, dependency và networking phù hợp.
- Một số cơ chế RMI dùng trong các hệ thống legacy hoặc công cụ quản trị, với các ràng buộc an ninh riêng.

Ví dụ ứng dụng **không dùng Activation** có thể tiếp tục triển khai RMI server bình thường trên JDK 17. Tuy nhiên, điều này chưa khẳng định mọi hình thức RMI legacy đều hoạt động: codebase downloading, dynamic class loading, Security Manager, serialization, JRMP connection và những thư viện đã cũ cần được khảo sát độc lập.

### 5.1. So sánh trực quan

| Khía cạnh | RMI thường | RMI Activation |
|---|---|---|
| Server object lifecycle | Ứng dụng tự tạo/export object | Có thể kích hoạt object theo registration và lời gọi |
| Thành phần đặc trưng | `UnicastRemoteObject`, `Registry` | `Activatable`, `ActivationDesc`, `rmid` |
| Service start | Do launcher/supervisor/application | Activation system có thể tham gia khởi tạo process |
| Lookup | Registry hoặc cơ chế lấy remote ref khác | Có thể sử dụng registry song song với activation reference |
| Phụ thuộc Java 17 | RMI APIs cơ bản vẫn có | Activation bị loại bỏ |
| Migration | Kiểm tra compatibility | Cần thay đổi kiến trúc lifecycle |

Đừng dùng từ “RMI không còn hỗ trợ” để mô tả vấn đề của một ứng dụng chỉ có lỗi ở `java.rmi.activation`. Diễn đạt chính xác giúp đội ngũ chọn giải pháp đúng phạm vi và tránh viết lại giao thức không cần thiết.

## 6. Lỗi biên dịch khi source còn dùng java.rmi.activation

Khi chuyển project sang compiler JDK 17+ với source còn import Activation API:

~~~java
import java.rmi.activation.Activatable;
import java.rmi.activation.ActivationID;
~~~

Compiler có thể báo package hoặc symbol không tồn tại. Ví dụ biểu hiện:

~~~text
error: package java.rmi.activation does not exist
error: cannot find symbol
    symbol: class ActivationID
~~~

Đây là lỗi **API đã bị loại bỏ khỏi JDK**, không phải đơn thuần vì package bị JPMS che. Những tùy chọn `--add-opens` hoặc `--add-exports` không tạo lại class đã mất.

Nếu module mới được đặt target Java 17 nhưng mã vẫn dựa trên Activation, sửa các flag không phải giải pháp. Cần thay cách cung cấp lifecycle hoặc thay thư viện API.

### 6.1. Thư viện biên dịch từ JDK cũ có thể thất bại ở runtime

Một JAR được compile sẵn với Java 8 có thể chứa tham chiếu tới class thuộc `java.rmi.activation`. Nó có class-file version cũ mà JVM Java 17 đọc được, nhưng khi cần nạp hoặc liên kết các lớp Activation, runtime có thể gặp:

~~~text
java.lang.NoClassDefFoundError: java/rmi/activation/Activatable
~~~

hoặc, nếu code tìm lớp bằng reflection:

~~~text
java.lang.ClassNotFoundException: java.rmi.activation.Activatable
~~~

Loại lỗi thực tế phụ thuộc cách class được tham chiếu và thời điểm JVM resolve, initialize hoặc load. Không suy từ “class file compatible” thành “mọi dependency đã tồn tại trong JDK mới”.

### 6.2. Lỗi chỉ xuất hiện khi khởi động một nhánh nghiệp vụ

Một số service có thể khởi động thành công nhưng chỉ đăng ký hoặc kích hoạt remote object sau một thao tác quản trị. Vì thế, smoke test “process started” không đủ. Cần kiểm tra đường đi đăng ký, lookup, invoke, process restart và phục hồi sau sự cố.

## 7. Lỗi vận hành: không còn rmid

Hệ thống cũ có thể có startup script:

~~~bash
# Ví dụ lịch sử; không dùng để khởi động trên JDK 17+
rmid -port 1098
~~~

`rmid` là activation daemon của RMI, không phải `rmiregistry`. Trên JDK 17+, công cụ `rmid` không còn được cung cấp, nên script có thể báo command not found hoặc không khởi chạy được daemon.

Có thể phát sinh một chuỗi sự cố:

1. Deploy JDK mới nhưng script vẫn cố chạy `rmid`.
2. Daemon không tồn tại, activation registration không được phục vụ.
3. Các remote reference cũ liên quan Activation không còn được kích hoạt theo thiết kế.
4. Client lookup có thể thành công trong một số trạng thái nhưng invocation thất bại; hoặc lookup cũng thất bại nếu binding không được tái tạo.
5. Monitoring chỉ nhìn process chính có thể bỏ sót sự cố ở cơ chế kích hoạt.

Không được thay tên `rmid` thành `rmiregistry` trong script rồi tuyên bố migration xong. Registry không lưu và thực thi activation descriptors.

### 7.1. Dữ liệu registration cũ

Hệ thống Activation có thể duy trì dữ liệu đăng ký và metadata trong vùng lưu của daemon. Khi bỏ Activation, cần biết những dữ liệu đó có ý nghĩa gì:

- Activation ID và reference nào đang được client giữ?
- Mapping logic giữa tên dịch vụ và implementation được lưu ở đâu?
- Startup properties và path tới implementation JAR nằm trong descriptor nào?
- Các cấu hình activation group có chứa credential hoặc JVM arguments không?
- Có state nghiệp vụ nào bị nhầm là được Activation tự lưu bền vững không?

Không nên mặc định có thể chuyển “database của `rmid`” trực tiếp vào RMI registry hoặc service manager. Cần trích xuất thông tin cấu hình cần thiết theo cách phù hợp trước khi tắt môi trường cũ và xây lại registration/lifecycle ở nền tảng mới.

## 8. Kiểm kê phụ thuộc Activation trong source, artifact và script

Trước khi sửa code, hãy tìm dấu hiệu trực tiếp và gián tiếp.

### 8.1. Tìm trong source và cấu hình

Với công cụ tìm kiếm văn bản như ripgrep:

~~~bash
rg -n 'java\.rmi\.activation|Activatable|ActivationID|ActivationDesc|ActivationGroup|ActivationSystem|\brmid\b' .
~~~

Kết quả cần được phân loại:

- Import Java trực tiếp.
- Fully qualified class name được cấu hình bằng string.
- Template code generation.
- Build script, deployment script, startup service.
- Tài liệu vận hành và các command cũ.
- Test fixture hoặc ví dụ chỉ nhằm minh họa.

Không phải mọi kết quả tìm thấy đều được thực thi. Cần xác nhận module liên quan còn chạy trên production không.

### 8.2. Kiểm tra dependency và bytecode

Nếu ứng dụng không import Activation nhưng JAR bên thứ ba sử dụng, cần phân tích:

- Compile classpath và runtime classpath thực tế.
- Danh sách JAR đóng gói hoặc do application server cung cấp.
- Dependency tree và phiên bản transitive dependency.
- Bytecode references trong class bị nghi ngờ.
- Release notes tương thích Java của thư viện.

Có thể dùng `jdeps` với môi trường phụ thuộc phù hợp để phân tích những thiếu hụt dependency:

~~~bash
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Chú ý: `jdeps --jdk-internals` chuyên tìm một số phụ thuộc JDK internal APIs; **nó không phải công cụ chuyên dụng để phát hiện các tham chiếu tới RMI Activation đã bị loại bỏ**. Nên kết hợp tìm kiếm source, kiểm tra dependency graph và thử compile/load dưới JDK mục tiêu.

Với fat JAR chứa nested JAR (chẳng hạn launcher framework), có thể phải tách hoặc phân tích riêng các JAR bên trong. Không kết luận “sạch” chỉ vì lệnh trên một JAR ngoài cùng không tìm ra phụ thuộc.

### 8.3. Kiểm tra runtime thật

Trên từng môi trường, ghi lại:

~~~bash
java -version
javac -version
~~~

Và kiểm tra startup configuration, systemd unit, Windows Service, container entrypoint, job scheduler, CI pipeline hoặc script triển khai có tham chiếu `rmid` không.

Có thể xem những module runtime còn cung cấp:

~~~bash
java --list-modules
~~~

Module `java.rmi` có thể vẫn xuất hiện, nhưng điều đó **không** chứng minh Activation còn tồn tại trong nó. Muốn xác định API đã bị gỡ phải kiểm tra release mục tiêu và class/package cụ thể.

## 9. Phân loại cách hệ thống thực sự sử dụng Activation

Không phải mọi ứng dụng chứa tên `Activatable` đều có cùng rủi ro. Nên chia thành các trường hợp:

| Trường hợp | Dấu hiệu | Chiến lược |
|---|---|---|
| Import còn trong mã không được build | Module/tool cũ nằm ngoài phạm vi deploy | Quyết định loại bỏ hoặc cô lập bằng bằng chứng |
| Compile-time dependency | Source dùng `ActivationID` hoặc `Activatable` | Refactor source và API design |
| Runtime library dependency | JAR cũ sử dụng Activation | Nâng/thay thư viện hoặc thay chức năng |
| Server Activation thực sự | Có `rmid`, registration, activation group | Thiết kế lại service lifecycle |
| Client giữ activatable references | Remote references được lưu hoặc chuyển qua hệ khác | Kiểm tra compatibility và re-discovery |
| Integration test lịch sử | Test khởi động `rmid` hoặc Activation daemon | Viết lại test theo lifecycle mới |
| Code generation/template | Generator phát code Activation | Cập nhật generator rồi sinh lại |
| Deployment phụ thuộc daemon | Script/config chuẩn bị `rmid` | Đổi hệ orchestration và startup |

Một phân tích chính xác sẽ làm rõ **vai trò của Activation**: chỉ là một chi tiết triển khai cũ, hay là yêu cầu nghiệp vụ quan trọng như khởi động theo yêu cầu, cách ly process hoặc tự phục hồi dịch vụ.

## 10. Chuyển từ Activation sang RMI thường với lifecycle bên ngoài

Khi client Java vẫn cần giao tiếp qua RMI và server interface còn phù hợp, phương án thay đổi tối thiểu thường là:

1. Giữ remote interface khi có thể.
2. Thay logic tạo activatable object bằng cách tạo và export đối tượng RMI thông thường.
3. Dùng RMI registry để đăng ký remote reference khi server process khởi động.
4. Dùng systemd, Windows Service, container supervisor hoặc orchestrator để quản lý process.
5. Lưu và phục hồi state nghiệp vụ qua database hoặc storage rõ ràng.
6. Cập nhật client discovery và retry khi server restart.
7. Kiểm tra cả registry port, exported object port, firewall và hostname được quảng bá.

Kiến trúc sau migration:

~~~text
             Service manager / orchestrator
                        |
               Start / restart server
                        |
                        v
     +-----------------------------------------+
     | Long-running JVM service                |
     |  - Construct implementation             |
     |  - Export UnicastRemoteObject           |
     |  - Bind remote reference in Registry    |
     |  - Handle remote requests               |
     +-----------------------------------------+
                 ^                 ^
                 | lookup          | remote calls
                 |                 |
             RMI registry        Client
                 ^
                 |
       Bind/rebind at startup
~~~

Nếu registry được tạo ngay trong server JVM, registry chết khi JVM chết. Nếu registry là process riêng, binding có thể tồn tại trong một số trường hợp nhưng remote object đã mất; client vẫn phải xử lý stale reference và server cần rebind sau restart. Vì vậy, **registry không thay thế cơ chế health check hoặc service discovery có vòng đời được quản lý**.

### 10.1. Khác biệt về semantics phải chấp nhận

RMI thường với server chạy liên tục không tự tái tạo **lazy activation** theo remote call. Nếu tính năng tiết kiệm tài nguyên bằng khởi động theo yêu cầu là yêu cầu cốt lõi, cần giải pháp orchestration hoặc thiết kế giao tiếp khác. Nếu chỉ cần “service hoạt động và tự khởi động lại”, process supervisor thường đơn giản và dễ quan sát hơn cơ chế Activation cũ.

## 11. Ví dụ mã Java RMI không dùng Activation trên JDK mới

Ví dụ dưới đây gồm một remote interface, implementation, server và client. Nó sử dụng các API RMI thông thường, **không import `java.rmi.activation.*`**.

### 11.1. Remote interface

File `src/example/rmi/GreetingService.java`:

~~~java
package example.rmi;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface GreetingService extends Remote {

    String greet(String name) throws RemoteException;
}
~~~

Remote methods cần khai báo `RemoteException` theo hợp đồng RMI để client nhận biết lỗi truyền thông từ xa.

### 11.2. Implementation

File `src/example/rmi/GreetingServiceImpl.java`:

~~~java
package example.rmi;

import java.rmi.RemoteException;

public final class GreetingServiceImpl implements GreetingService {

    @Override
    public String greet(String name) throws RemoteException {
        return "Xin chao, " + name;
    }
}
~~~

Implementation không cần mở rộng `Activatable`. Nó là một đối tượng Java bình thường được export bởi server.

### 11.3. Server

File `src/example/rmi/GreetingServer.java`:

~~~java
package example.rmi;

import java.rmi.Remote;
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;
import java.rmi.server.UnicastRemoteObject;

public final class GreetingServer {

    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingServiceImpl();

        // Export service endpoint on a stable port for deployment/firewall.
        Remote stub = UnicastRemoteObject.exportObject(service, 12099);

        // Demo: registry runs inside this same JVM process.
        Registry registry = LocateRegistry.createRegistry(1099);
        registry.rebind("GreetingService", stub);

        System.out.println("GreetingService ready on port 12099");
    }
}
~~~

Ở ví dụ này:

- Port 1099 dành cho RMI registry.
- Port 12099 dành cho remote object endpoint.
- Process phải được khởi chạy bằng công cụ quản lý vòng đời bên ngoài.
- Khi server khởi động lại, nó tạo/export object rồi đăng ký lại binding.
- Dùng port cố định giúp dễ cấu hình firewall; production cần cân nhắc TLS, xác thực và kiến trúc mạng.

Đây là ví dụ giáo dục tối giản, chưa bao gồm shutdown hooks, health checks, metrics, retry policy hoặc hardening bảo mật.

### 11.4. Client

File `src/example/rmi/GreetingClient.java`:

~~~java
package example.rmi;

import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public final class GreetingClient {

    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "localhost";

        Registry registry = LocateRegistry.getRegistry(host, 1099);
        GreetingService service =
                (GreetingService) registry.lookup("GreetingService");

        System.out.println(service.greet("Mai"));
    }
}
~~~

Client phải có interface `GreetingService` tương thích trên classpath. Nó không yêu cầu các class implementation server nằm trên client classpath.

### 11.5. Biên dịch và chạy

Ví dụ với shell Linux/macOS từ thư mục project:

~~~bash
mkdir -p out
javac --release 17 -d out src/example/rmi/*.java

# Terminal 1
java -cp out example.rmi.GreetingServer

# Terminal 2
java -cp out example.rmi.GreetingClient localhost
~~~

Khi chạy trên môi trường mạng thực, cần kiểm tra địa chỉ máy chủ được nhúng trong remote reference. Trong một số trường hợp NAT, container hoặc hostname được JVM tự chọn không truy cập được từ client. Có thể cần cấu hình `java.rmi.server.hostname` một cách phù hợp với mạng triển khai và bảo đảm cả registry port lẫn exported service port thực sự mở.

Ví dụ này chứng minh **RMI thông thường vẫn có thể được thiết kế và biên dịch bằng JDK 17**. Nó không chứng minh remote references cũ của RMI Activation tương thích trực tiếp hoặc có thể được sử dụng lại không đổi.

## 12. RMI registry không có nhiệm vụ khởi động service

Một lỗi thiết kế migration phổ biến là nghĩ rằng client gọi `Registry.lookup` thì JVM server sẽ được tạo ra. Với RMI thông thường:

- `lookup` chỉ tra cứu tên đã được đăng ký.
- `rebind` cập nhật binding đến remote reference.
- Registry không tự tạo implementation class hoặc process.
- Khi process xuất remote object dừng, reference có thể thành stale.
- Khi process mới chạy, nó phải tự export và đăng ký lại.
- Nếu client giữ reference cũ, có thể phải lookup lại và thử yêu cầu mới theo chính sách an toàn.

Ví dụ client phải chịu được:

~~~text
Client lookup ok
     |
     v
Server restart between lookup and invoke
     |
     v
RemoteException / connection failure
     |
     v
Re-discover service and retry if operation is safe
~~~

Việc retry các thao tác cập nhật tiền, tạo đơn hàng hoặc thực hiện thanh toán phải cân nhắc **idempotency**, correlation ID và trạng thái commit. Không retry mù quáng vì client không luôn biết thao tác trước đó đã được server xử lý hay chưa.

Nếu hệ thống Activation cũ cung cấp trải nghiệm “gọi một object bất kể process đang chạy”, migration cần giữ **hợp đồng bên ngoài** bằng cơ chế quản lý service và xử lý lỗi rõ ràng, chứ không chỉ thay một import.

## 13. Khi nào cần thay bằng systemd, container orchestrator hoặc scheduler?

Việc bỏ Activation khiến quản lý vòng đời process phải chuyển sang hạ tầng hoặc application logic. Lựa chọn phụ thuộc nhu cầu.

| Nhu cầu | Cơ chế có thể cân nhắc | Khác biệt so với Activation |
|---|---|---|
| Service chạy liên tục | systemd, Windows Service, container supervisor | Luôn khởi chạy và giữ process sẵn sàng |
| Tự khởi động lại khi crash | Restart policy của supervisor/orchestrator | Thường phục hồi process chủ động, không đợi invocation |
| Triển khai và scale nhiều replica | Container orchestration, load balancing | Cần thiết kế service discovery và state |
| Khởi chạy theo sự kiện | Queue consumer, scheduler, job controller | Trigger là sự kiện/job thay vì RMI activation reference |
| Khởi tạo logic tốn chi phí khi có request | Lazy initialization trong process đang chạy | Process vẫn tồn tại trước khi request đến |
| Tiết kiệm tài nguyên khi không có request | Cơ chế scale-to-zero hoặc on-demand service platform phù hợp | Không tương thích drop-in với giao thức RMI/JRMP |
| Nhiều service nhỏ chia sẻ tài nguyên | Application server/service host có quản lý lifecycle | Khác mô hình activation group và remote object identity |

Không nên mô tả systemd socket activation hoặc scale-to-zero như giải pháp thay thế trực tiếp mà không cần sửa hệ thống. RMI có cách thiết lập transport/registry và remote reference riêng; mọi cơ chế khởi động theo kết nối cần được thiết kế, kiểm tra tương thích giao thức và quản lý timeout/lookup phù hợp.

### 13.1. Ví dụ service chạy liên tục

Trong một triển khai Linux, có thể dùng systemd service để khởi động JVM. File ví dụ:

~~~ini
[Unit]
Description=Legacy RMI service (without RMI Activation)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rmi-service
WorkingDirectory=/opt/orders
ExecStart=/usr/bin/java -jar /opt/orders/orders-service.jar
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
~~~

Đây là cấu hình minh họa về **process lifecycle**, không áp dụng trực tiếp cho ví dụ `GreetingServer` phía trên vì ví dụ đó dùng `-cp` và main class thay vì executable JAR. Trước khi áp dụng vào môi trường thật, cần điều chỉnh đường dẫn, người dùng, quyền, secret handling, logging, memory options, restart behavior và artifact launch command.

Một process supervisor không tự đảm bảo remote service đã đăng ký thành công trong registry; cần readiness check phù hợp.

## 14. Xử lý state, identity và sự bền vững dữ liệu

RMI Activation từng cho phép **đăng ký metadata kích hoạt** và tạo đối tượng khi cần. Điều đó không đồng nghĩa activation daemon lưu state nghiệp vụ của đối tượng.

Khi thay Activation, cần tách:

1. **Identity của dịch vụ:** tên logic hoặc service key mà client dùng để tìm.
2. **Identity của remote object/reference:** handle trong RMI transport, có thể thay đổi sau restart.
3. **Configuration:** thông tin constructor, port, JVM flags, group description.
4. **Business state:** dữ liệu đơn hàng, session, job, công việc dang dở.
5. **Runtime state:** cache, thread, socket, connection pool, in-memory counters.

Nếu code cũ giữ một `ActivationID` làm identifier bền vững, không nên thay bằng serialized RMI stub của `UnicastRemoteObject` rồi kỳ vọng nó ổn định vĩnh viễn. Dùng application-level IDs trong database hoặc service registry là hướng thiết kế rõ ràng hơn.

### 14.1. Phục hồi sau restart

Một service hiện đại thường cần:

- Đọc cấu hình từ file, environment hoặc config service.
- Nạp trạng thái bền vững từ data store khi khởi động.
- Khôi phục pending tasks theo semantics của ứng dụng.
- Khởi tạo dependencies và export remote object.
- Đăng ký endpoint sau khi sẵn sàng phục vụ.
- Xóa/rebind registration khi stop/restart nếu cần.
- Có log, metrics, health và failure escalation.

Nếu mất process trong khi xử lý request, cần quy tắc transaction và retry để tránh mất hoặc thực thi trùng công việc. RMI Activation trước đây cũng không thay thế được nghiệp vụ đảm bảo exactly-once.

## 15. Hệ thống dùng client cũ: cần kế hoạch tương thích giao thức

Một migration server chưa đủ nếu client đang giữ hoặc lưu **activatable remote reference**.

Có thể gặp:

- Client lookup qua registry lấy một stub gắn với Activation.
- Remote reference đã được serialize để lưu database/file.
- Một hệ thống trung gian gửi remote reference cho client khác.
- Client dùng thư viện generated code liên quan `ActivationID`.
- Các version client triển khai chậm hơn server, tạo giai đoạn cùng tồn tại.

Sau khi bỏ Activation, có thể phải:

1. Chuyển client sang tra cứu endpoint mới theo service name.
2. Cập nhật thư viện client để bỏ type `java.rmi.activation` khỏi API.
3. Cập nhật nơi lưu serialized references, không coi dữ liệu cũ là reference đang hoạt động.
4. Thay bằng identifier logic và dynamic service lookup.
5. Thiết kế versioning cho interface/method signatures nếu thay đổi.
6. Phân phối thay đổi theo thứ tự phù hợp: client readiness, server deployment, migration/rollback window.

Một cách tiếp cận an toàn là tránh để client lâu dài phụ thuộc implementation class hoặc serialized remote reference. Hợp đồng nên được thể hiện bằng remote interface, service name, dữ liệu truyền nhận và quy tắc lỗi/tái thử.

## 16. Lựa chọn viết lại giao tiếp: HTTP, gRPC, messaging

Giữ RMI thường có thể giúp giảm phạm vi migration, nhưng không phải lúc nào cũng là đích kiến trúc tốt nhất. Nếu hệ thống đang cải tổ deployment hoặc có nhiều ngôn ngữ client, có thể cân nhắc API hoặc message-based architecture.

| Hướng | Khi phù hợp | Điều cần cân nhắc |
|---|---|---|
| Giữ RMI, bỏ Activation | Client Java hiện tại nhiều; muốn đổi ít nhất | RMI networking, registry, serialization, versioning |
| HTTP/REST | Public service API, nhiều nền tảng | HTTP semantics, contract, authentication, payload format |
| gRPC | RPC typed contracts, nhiều ngôn ngữ, streaming | Protobuf, load balancing, tooling, backward compatibility |
| Messaging/event-driven | Xử lý bất đồng bộ, yêu cầu durable delivery | At-least-once, idempotency, consumer lifecycle, ordering |
| Scheduler/job service | Công việc chạy theo lịch hoặc yêu cầu có trạng thái | Job identity, persistence, retry, monitoring |
| In-process module | Không cần phân tán giữa các process | Thay đổi deployment và failure isolation |

Không có một công nghệ nào tự thay thế hoàn toàn semantics của RMI Activation. Cần viết lại **hợp đồng sử dụng**, **lifecycle**, **error handling** và **state management**, không chỉ chuyển cú pháp client call.

### 16.1. Cách quyết định phạm vi thay đổi

Nếu mục tiêu là lên JDK 17 nhanh và an toàn, giữ RMI thường có thể là phương án ít rủi ro. Nếu RMI Activation cũ đi cùng với nhiều vấn đề vận hành, security hoặc cross-language integration, có thể dùng migration này để hoạch định chuyển dần sang một giao thức mới. Nên tách hai quyết định và dùng bằng chứng để kiểm soát rủi ro.

## 17. RMI, Security Manager và những thay đổi liên quan nhưng độc lập

Hệ thống RMI cũ có thể sử dụng security policy, codebase loading, Java Security Manager, custom socket factory hoặc dynamic class loading. Những tính năng này có lịch sử thay đổi riêng ngoài việc RMI Activation bị loại bỏ.

Các điểm cần khảo sát:

- JVM flags và policy files phục vụ cơ chế security cũ.
- Download class từ codebase và giả định về class loading.
- Serialized data và những loại object có thể deserialization qua network.
- SSL/TLS hoặc custom RMI socket factories.
- Firewall và server address/hostname trong remote references.
- Authentication, authorization và audit.
- Deserialization filters và hạn chế nguồn dữ liệu không đáng tin cậy.
- Quy tắc timeout, reconnect, retry và exception handling.

**Bỏ Activation không tự giải quyết bảo mật của RMI.** Nếu hệ thống tiếp tục dùng Java serialization qua mạng, cần kiểm tra trust boundary và bộ lọc serialization phù hợp với JDK/runtime mục tiêu. Hạn chế truy cập registry và remote ports ở mạng tin cậy, tránh mở endpoint không kiểm soát.

Khi nâng JDK lớn, cũng cần kiểm tra tình trạng hỗ trợ Security Manager trên phiên bản mục tiêu và cách thư viện RMI của ứng dụng phụ thuộc vào cơ chế đó. Không mặc định các policy/cấu hình lịch sử còn có tác dụng giống nhau.

## 18. Các lỗi sau migration và hướng điều tra

| Biểu hiện | Giả thuyết chính | Hành động |
|---|---|---|
| `package java.rmi.activation does not exist` | Source vẫn dùng Activation API đã bị gỡ | Refactor hoặc thay dependency |
| `rmid: command not found` | Script vẫn khởi chạy daemon cũ | Thay lifecycle script/service manager |
| `NoClassDefFoundError: ... Activatable` | JAR cũ tham chiếu API Activation runtime không có | Nâng/thay JAR, loại bỏ Activation |
| `ClassNotFoundException` khi load class Activation bằng reflection | Tên class cũ trong config/plugin | Thay config/implementation |
| `NotBoundException` khi lookup | Server chưa bind tên hoặc dùng sai registry | Khởi tạo và rebind đúng lúc |
| `ConnectException` / `ConnectIOException` | Server không chạy, host/port/firewall không phù hợp | Kiểm tra network và exported endpoint |
| Lỗi sau server restart | Client giữ stale remote reference | Lookup lại và retry an toàn |
| Stub chứa host nội bộ không tới được | RMI export hostname/NAT không đúng | Cấu hình host và mạng |
| Process chạy nhưng client vẫn lỗi | Registry sẵn nhưng object chưa export/bind hoặc port bị chặn | Kiểm tra readiness toàn tuyến |
| Công việc bị thực hiện hai lần | Retry không có idempotency | Thêm request ID và transaction semantics |
| Startup ổn nhưng mất dữ liệu | State cũ chỉ nằm trong RAM | Thiết kế persistence và restore |

Không nên đọc một `RemoteException` rồi kết luận Activation bị loại bỏ. RemoteException có nhiều nguyên nhân: TCP reset, timeout, serialization, server crash, lookup, authentication hoặc failure trong application. Cần stack trace, log hai phía và trạng thái service manager.

## 19. Kiểm thử migration không chỉ dừng ở compile

Để chứng minh hệ thống không còn lệ thuộc Activation, cần kiểm tra cả chức năng và vận hành.

### 19.1. Kiểm tra tĩnh

- Source không còn import `java.rmi.activation.*` trong đường build đang sử dụng.
- Dependency không còn class thực sự dùng Activation API.
- Deployment scripts, Docker entrypoint và service manager không gọi `rmid`.
- Không còn config/serialized object cần activation-specific reference.
- Artifact compile bằng JDK và Java release mục tiêu.

### 19.2. Kiểm tra chức năng

- Server tạo/export remote object thành công.
- Client lookup đúng service name.
- Remote call trả kết quả và báo lỗi đúng.
- Authentication, authorization và input validation được giữ nguyên.
- Dữ liệu truyền qua remote interface tương thích trong phạm vi client hỗ trợ.
- Các nhánh hiếm hoặc administrative calls vẫn hoạt động.

### 19.3. Kiểm tra vòng đời

Các kịch bản bắt buộc nên gồm:

1. Server chưa chạy, client cần nhận lỗi/retry theo thiết kế.
2. Supervisor khởi động server và đăng ký service.
3. Client gọi thành công từ host/network thật.
4. Server crash giữa hai remote calls.
5. Supervisor restart process và remote object được export lại.
6. Client đang giữ stub cũ gặp lỗi rồi re-discover endpoint.
7. Restart registry, kiểm tra binding được tạo lại theo topology thực tế.
8. Database/message broker tạm thời không khả dụng khi startup.
9. Triển khai rolling update trong môi trường nhiều phiên bản client.
10. Rollback theo kế hoạch nếu có lỗi critical.

Với thao tác không idempotent, không dùng phép thử retry gây ghi dữ liệu trùng mà không có môi trường và quy tắc bù trừ.

### 19.4. Kiểm tra phi chức năng

So sánh với baseline:

- Thời gian từ khởi động process đến readiness.
- Latency cold start và steady state.
- Thông lượng và p95/p99 remote call latency.
- CPU, heap, thread, socket và connection count.
- Tốc độ phục hồi sau crash.
- Số lần retry và thất bại khi lookup.
- Timeouts, queue size và saturation trong tình huống tải lớn.

Thay từ activation theo yêu cầu sang service chạy liên tục có thể làm tăng tài nguyên nền nhưng giảm cold start latency. Phải đo và đánh giá theo yêu cầu vận hành của hệ thống, không mặc định một chiều tốt hơn.

## 20. Quy trình nâng JDK cho hệ thống còn RMI Activation

### Bước 1: Ghi nhận hiện trạng

Lưu JDK version, build tool, artifact, danh sách remote interfaces, activation descriptors, group configuration, server/client topology, rmid startup scripts, registry bindings và kịch bản recovery. Xác định application owner và phụ thuộc bên ngoài.

### Bước 2: Xác định phạm vi loại bỏ

Phân nhóm thành import trực tiếp, dependency thư viện, daemon vận hành, serialized reference và script/test. Ghi rõ từng thành phần có còn dùng trong production hay chỉ là code cũ không hoạt động.

### Bước 3: Chọn kiến trúc đích

Quyết định có giữ RMI transport không. Nếu giữ, chọn cách export objects, registry topology, process supervisor, service discovery và state store. Nếu chuyển HTTP/gRPC/messaging, cần thiết kế API contract và migration client.

### Bước 4: Thay server lifecycle

Bỏ đăng ký Activation, chuyển startup logic sang application bootstrap và/orchestrator, export object bằng RMI thường khi thích hợp, bind/rebind tên theo readiness, xử lý graceful shutdown và restart.

### Bước 5: Điều chỉnh client

Không lưu hoặc dùng activation-specific remote references. Client cần tìm endpoint mới, xử lý stale stub, timeout, retry an toàn và versioning. Nếu cần song song client cũ/mới, thiết kế bridge chỉ khi còn runtime cũ và ranh giới giao tiếp được hỗ trợ; không mặc định Java 17 chạy được Activation server.

### Bước 6: Xử lý dữ liệu và cấu hình

Di chuyển service metadata cần thiết từ activation descriptors sang config store; chuyển state nghiệp vụ vào persistence thích hợp. Ghi lại các JVM flags, ports, credentials và biến môi trường theo mô hình deploy mới.

### Bước 7: Biên dịch, đóng gói và thử trên JDK mới

Dùng toolchain mục tiêu và `--release` phù hợp. Kiểm tra source, dependencies, class-file version và startup. Chạy integration tests trong môi trường gần production nhất có thể.

### Bước 8: Kiểm tra sự cố và rollback

Mô phỏng crash, restart, network partition, registry failure, stale client reference và concurrent requests. Quy trình rollback phải tính tới sự khác biệt dữ liệu, interface và deployment; không chỉ thay JDK binary là có thể quay lại nếu state hoặc client đã được migrate.

### Bước 9: Loại bỏ thành phần cũ

Chỉ sau khi xác nhận không còn consumer, dừng `rmid` ở môi trường cũ, xóa các scripts và cấu hình lỗi thời, cập nhật monitoring, runbook và tài liệu đào tạo vận hành. Không xóa dữ liệu lịch sử trước khi xác nhận nghĩa vụ lưu trữ và rollback.

## 21. Mẫu bảng quản lý thay đổi

Một project có thể lập bảng:

| Hạng mục | Hiện trạng | Thay thế | Bằng chứng hoàn thành |
|---|---|---|---|
| Server object registration | `Activatable` / `ActivationDesc` | `UnicastRemoteObject` + registry hoặc giao thức mới | Source diff, compile |
| Process activation | `rmid` | Supervisor/orchestrator | Startup/restart test |
| Activation group flags | Group descriptor | Service/container config | Deployment review |
| Client reference | Activatable reference | Lookup logic mới | Client integration test |
| Metadata persistence | Activation daemon log | Config store | Config migration verification |
| Business state | In-memory hoặc store cũ | Durable persistence | Recovery test |
| Monitoring | Kiểm tra `rmid`/JVM cũ | Liveness/readiness/metrics | Alert test |
| Security | Policy/RMI flags cũ | Updated network/security config | Security validation |
| JDK baseline | Java 8/11 | Java 17+ target | Build/run reports |
| Rollback | Restore activation environment | Đường lui theo giai đoạn | Runbook rehearsal |

Một cột quan trọng là **bằng chứng**: việc đổi code chưa chứng minh thay đổi đã được deploy và phục hồi đúng. Báo cáo nên lưu runtime version, artifact checksum, cấu hình launch và kết quả test.

## 22. Các sai lầm thường gặp

### 22.1. “Java 17 bỏ RMI hoàn toàn”

Sai về phạm vi. Java RMI API cơ bản và module `java.rmi` tiếp tục tồn tại; phần bị gỡ là **RMI Activation**. Cách xử lý lỗi phụ thuộc thư viện và thiết kế có dùng Activation hay không.

### 22.2. “Đổi sang rmiregistry là xong”

Không đúng. RMI registry lưu remote name/reference, không tự khởi động implementation theo activation descriptors. Phải có process lifecycle và registration mới.

### 22.3. “Thêm --add-opens là hồi sinh được Activation”

Không đúng. `--add-opens` có thể giải quyết một số lỗi reflective access tới package còn tồn tại; nó không bổ sung `java.rmi.activation` hay `rmid` đã bị loại bỏ.

### 22.4. “Compile thành công nghĩa runtime ổn”

Không đúng. Một thư viện cũ được compile từ JDK 8 vẫn có thể chứa tham chiếu tới Activation bị thiếu trên JDK 17. Ngoài ra, remote call còn phụ thuộc network, registry, serialization, class loader và service lifecycle.

### 22.5. “Supervisor restart là tương đương kích hoạt object theo yêu cầu”

Không nhất thiết. Restart policy phục hồi process bị dừng, còn lazy activation theo remote invocation là semantics khác. Nếu cold start theo yêu cầu là tính năng bắt buộc, cần thiết kế đặc thù cho workload.

### 22.6. “Giữ nguyên serialized remote references là tương thích”

Không an toàn. Client giữ reference thuộc Activation cũ có thể không hoạt động với server đã thay thế. Cần cơ chế lookup mới và xử lý client upgrade.

### 22.7. “Dữ liệu do rmid giữ là state ứng dụng”

Không nên mặc định. Activation metadata và business state có vai trò khác nhau. State nghiệp vụ cần được kiểm kê, di chuyển và kiểm thử phục hồi riêng.

## 23. Câu hỏi thực tế khi lựa chọn phương án

**Ứng dụng chỉ dùng `java.rmi.registry.Registry` và `UnicastRemoteObject`, không có `rmid`, có cần thay RMI không?**

Không phải vì JEP 407. Vẫn cần xác minh JDK, dependency, security và runtime; nhưng đó không phải một hệ Activation cần thiết kế lại.

**Ứng dụng có source import `java.rmi.activation.*` nhưng code không bao giờ chạy, có thể giữ lại không?**

Nếu module còn được biên dịch bằng JDK 17+, import và symbol không tồn tại có thể làm build lỗi trước khi xét runtime. Nên loại bỏ, cô lập hợp lý hoặc refactor phần mã đó thay vì để “dead code” cản migration.

**Có thể dùng một JAR tự thêm java.rmi.activation vào classpath để chạy lại như trước không?**

Không có cơ sở để xem đó là thay thế tương thích đầy đủ. Activation gắn với nhiều thành phần JDK và daemon `rmid` đã bị loại bỏ. Không nên kỳ vọng chỉ thêm API stubs sẽ khôi phục cơ chế kích hoạt cũ.

**Có cần chuyển ứng dụng sang JPMS để giải quyết RMI Activation không?**

Không. Ngược lại, ứng dụng có thể ở classpath và vẫn phải bỏ Activation nếu chạy JDK 17+. JPMS modularization là quyết định riêng.

**Có nên chuyển thẳng sang REST hoặc gRPC không?**

Tùy mục tiêu dài hạn. Nếu cần giảm rủi ro nhanh, chuyển Activation sang RMI thường và lifecycle được quản lý có thể ít thay đổi hơn. Nếu cần interoperability, scalability và API contract mới, có thể lập kế hoạch chuyển giao thức theo các giai đoạn với test tương thích client.

**Nếu đối tượng chỉ được dùng vài lần mỗi ngày thì làm sao giữ khởi động theo yêu cầu?**

Cần tách nhu cầu: có thể chấp nhận service chạy nền không, hay thật sự cần scale-to-zero/lazy start? Nếu cần on-demand, thiết kế trigger/job/queue/orchestration phù hợp và chấp nhận sự khác biệt so với RMI Activation reference. Nên đo cold start và xử lý timeout/retry của client.

## 24. Những nguyên tắc cần ghi nhớ

- **RMI Activation bị đánh dấu deprecated for removal trong Java 15 (JEP 385) và bị loại bỏ trong Java 17 (JEP 407).**
- **Java RMI thông thường không đồng nghĩa RMI Activation.** Các API `Remote`, `UnicastRemoteObject` và `Registry` vẫn là những thành phần riêng.
- **`rmid` không phải `rmiregistry`.** Registry không khởi động process theo registration của Activation.
- **Không sửa lỗi API bị loại bỏ bằng module flags.** `--add-opens`/`--add-exports` không mang lại class hoặc daemon đã mất.
- **Phải kiểm kê cả source, thư viện, bytecode, startup scripts và client references.** Activation có thể ẩn trong dependency hoặc vận hành.
- **Thay đổi vòng đời là trọng tâm.** Cần người quản lý process, startup/restart, export, bind, health check và state recovery.
- **Lazy activation và always-on service không giống nhau.** Cần làm rõ semantic requirement trước khi chọn giải pháp.
- **Giữ RMI thường là một lựa chọn hợp lệ** nếu phù hợp client, deployment và security; viết lại giao thức là một quyết định riêng.
- **Test phải bao gồm lỗi thật và restart**, không chỉ biên dịch thành công hoặc kiểm tra process khởi động.
- **Tách metadata activation và business state.** Đừng giả định daemon cũ là kho lưu dữ liệu nghiệp vụ.
- **Quy trình chuyển đổi phải xét compatibility client và rollback** nếu nhiều phiên bản cùng hoạt động.

Khi nâng cấp hệ thống Java còn dùng cơ chế kích hoạt RMI cũ, câu hỏi chính không phải “làm sao bật lại `rmid` trên JDK mới?” mà là **“dịch vụ cần được khởi tạo, tìm kiếm, giám sát và phục hồi như thế nào khi không còn Activation?”**. Trả lời bằng một thiết kế lifecycle rõ ràng, đầu vào/cấu hình được kiểm soát, giao tiếp tương thích và kiểm thử toàn tuyến sẽ giúp loại bỏ phụ thuộc lịch sử mà vẫn giữ được khả năng vận hành của hệ thống trên JDK hiện đại.
