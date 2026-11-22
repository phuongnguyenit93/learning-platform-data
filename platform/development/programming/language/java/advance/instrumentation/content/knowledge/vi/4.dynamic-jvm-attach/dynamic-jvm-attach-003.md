# Gắn vào JVM bằng `VirtualMachine.attach` với định danh đã xác nhận

> **Mục tiêu:** Kết nối có kiểm soát tới **đúng một JVM đang chạy** bằng Java Attach API (`jdk.attach`), dựa trên định danh đã được kiểm chứng trước khi gọi `VirtualMachine.attach(...)`. Bài học làm rõ `id`/PID/`VirtualMachineDescriptor`, các bước xác nhận danh tính, thời điểm attach và detach, một thí nghiệm Java 17+ có thể chạy, những sai lầm khi có nhiều JVM cùng tên và giới hạn kỹ thuật của cơ chế attach.

## 1. Bài toán: biết PID chưa chắc đã biết đúng JVM

Trên một máy chủ có thể đồng thời tồn tại:

```text
PID 3180  java -jar orders-service.jar        (môi trường thử nghiệm)
PID 4921  java -jar orders-service.jar        (môi trường phục vụ thật)
PID 7314  java -jar worker-service.jar
```

Nếu công cụ nhận một chuỗi `"4921"` rồi gọi ngay `VirtualMachine.attach("4921")`, nó đang giả định PID chính là JVM muốn làm việc. Giả định này có thể sai nếu người vận hành sao chép nhầm PID, nếu hai JVM có cùng command line, nếu một container có namespace PID khác, hoặc nếu process cũ đã thoát và hệ điều hành **tái sử dụng PID**.

Với công cụ instrumentation, lỗi chọn mục tiêu đặc biệt nghiêm trọng: bước sau attach có thể đọc thông tin không đúng ứng dụng hoặc yêu cầu JVM tải agent. Vì vậy, trước khi attach cần **xác nhận danh tính mục tiêu từ bằng chứng độc lập**, và ngay sau attach cần kiểm tra tiếp trước khi thực hiện tác vụ có ảnh hưởng.

**Bài học này tập trung vào attach theo một định danh đã xác nhận.** Thí nghiệm chỉ đọc một system property của JVM mục tiêu rồi `detach`; không gọi `loadAgent` và không biến đổi bytecode.

## 2. Attach API thực chất làm gì?

JDK cung cấp module **`jdk.attach`**, package `com.sun.tools.attach`. Lớp trung tâm là `VirtualMachine`.

- `VirtualMachine.list()`: trả danh sách các `VirtualMachineDescriptor` mà những attach provider được cài đặt có thể liệt kê.
- `VirtualMachineDescriptor.id()`: định danh **phụ thuộc implementation/provider**; ở nhiều JVM trên hệ điều hành phổ biến, giá trị này là PID dạng chuỗi.
- `VirtualMachineDescriptor.displayName()`: tên mô tả dành cho con người; **không phải khóa định danh duy nhất**.
- `VirtualMachineDescriptor.provider()`: provider tương ứng với descriptor.
- `VirtualMachine.attach(String id)`: thử attach qua các provider được cài đặt bằng chuỗi định danh.
- `VirtualMachine.attach(VirtualMachineDescriptor descriptor)`: attach thông qua **provider của descriptor đã chọn**.
- `vm.getSystemProperties()`: đọc system properties hiện tại của JVM mục tiêu.
- `vm.detach()`: đóng kết nối attach của công cụ tới JVM mục tiêu.

Kết nối attach thông thường là cơ chế quản trị **cục bộ** do JVM/provider và hệ điều hành triển khai. `VirtualMachine.attach(...)` **không tự động gọi `agentmain`** và cũng không tự động chèn mã vào class. Việc yêu cầu nạp Java agent là thao tác riêng (`vm.loadAgent(...)`), chỉ nên thực hiện sau khi danh tính đã xác nhận và có đúng quyền vận hành.

Sơ đồ:

```text
Người vận hành xác định ứng dụng cần kết nối
                  │
                  ▼
Thông tin độc lập: PID + thời điểm start + user + command
                  │
                  ▼
VirtualMachine.list() → chọn chính xác một descriptor
                  │
                  ▼
Kiểm tra lại process còn sống / không đổi
                  │
                  ▼
VirtualMachine.attach(descriptor)
                  │
                  ▼
Đối chiếu danh tính trong target (chỉ đọc)
                  │
          ┌───────┴────────┐
          │ đúng           │ không khớp
          ▼                ▼
  tác vụ được phép      từ chối tiếp tục
          │                │
          └───────┬────────┘
                  ▼
            vm.detach()
```

Hai ý quan trọng:

1. **Discovery không phải xác thực:** việc một JVM xuất hiện trong `VirtualMachine.list()` chỉ chứng tỏ provider liệt kê được nó tại thời điểm đó, không chứng tỏ đó là đúng service.
2. **Attach không đồng nghĩa thực thi tác vụ:** mở kết nối chỉ là một bước. Công cụ phải tự kiểm soát thao tác được gọi trên kết nối đó.

## 3. `id`, PID và `displayName`: dùng đúng vai trò

### 3.1. `VirtualMachineDescriptor.id()` không được đặc tả là PID trong mọi môi trường

Trong HotSpot/JDK thông dụng, `VirtualMachineDescriptor.id()` thường chính là PID hệ điều hành biểu diễn bằng chuỗi. Tuy nhiên API mô tả nó là **implementation-dependent identifier**. Một `AttachProvider` khác có thể dùng cách định danh khác.

Vì vậy:

```java
// Chỉ là ví dụ cho môi trường mà provider dùng PID:
String vmId = Long.toString(targetPid);
```

Đoạn này **không phải quy tắc tổng quát** cho mọi JVM/provider. Nếu công cụ cần đối chiếu `ProcessHandle.of(pid)`, trước hết phải có căn cứ rằng `id()` của provider đang dùng ánh xạ đúng sang PID nhìn từ namespace hiện tại.

### 3.2. `displayName` chỉ giúp người đọc phân biệt

Một JVM có thể hiển thị `com.example.Server`, `app.jar`, một chuỗi command hoặc chỉ chính ID tùy cách tạo descriptor. Hai tiến trình chạy cùng JAR có thể có cùng `displayName`. Vì thế không được tự động “lấy phần tử đầu tiên có tên chứa `orders`”.

Nên kiểm tra kết hợp:

| Bằng chứng | Có thể lấy từ đâu? | Giá trị và giới hạn |
| --- | --- | --- |
| **PID hoặc provider ID** | Log khi khởi động, công cụ quản lý process, `descriptor.id()` | Chọn ứng viên; có thể bị tái sử dụng hoặc khác namespace |
| **Thời điểm process bắt đầu** | `ProcessHandle.Info.startInstant()` hoặc công cụ OS | Phân biệt process mới với process cũ tái sử dụng PID; thông tin có thể không được cấp |
| **User chạy process** | `ProcessHandle.Info.user()` / OS | Giúp xác nhận chủ thể vận hành; không thay thế xác thực |
| **Executable/command line** | `ProcessHandle.Info.commandLine()` / OS | Phân biệt ứng dụng; có thể thiếu, bị rút gọn hoặc trùng nhau |
| **Descriptor/provider** | `VirtualMachine.list()` | Xác nhận JVM ứng viên được provider nhận diện tại thời điểm khám phá |
| **Dấu hiệu do chính ứng dụng phát ra** | Log/console lúc chạy; sau attach có thể so system property hoặc dữ liệu quản trị | Đối chiếu chéo; một marker nhìn thấy được **không phải mật khẩu hay bằng chứng chống giả mạo** |

Ở môi trường thực, nguồn xác nhận mạnh hơn có thể là process record từ supervisor/orchestrator, instance ID của lần triển khai, container ID và metadata khởi động. Không dùng một tên hiển thị hoặc PID đơn lẻ làm cơ sở duy nhất.

### 3.3. PID reuse: tại sao cần thời điểm khởi động?

Giả sử tiến trình A có PID `3180` lúc 10:00 và thoát lúc 10:05. Sau đó OS có thể cấp lại PID `3180` cho tiến trình B. Nếu công cụ giữ ID cũ trong cache, `attach("3180")` ở 10:10 có thể nối vào B.

Đối chiếu `(PID, startInstant)` giúp phát hiện sự thay đổi này trong những môi trường mà OS cung cấp thời điểm bắt đầu chính xác. Cần **kiểm tra lại ngay sát thời điểm attach và sau attach**, vì đọc danh sách và kết nối là hai thao tác tách rời, không tạo thành một giao dịch nguyên tử.

## 4. Quy trình attach với định danh đã được xác nhận

**Bước 1 — Xác định mục tiêu được phép thao tác.** Người vận hành chỉ rõ tên service, instance/deployment và môi trường mong muốn. Với ví dụ học tập, ứng dụng mục tiêu tự in PID, thời điểm start và marker lúc khởi động.

**Bước 2 — Thu PID/ID từ nguồn đáng tin.** Lấy PID từ chính process đang được quản lý hoặc từ log của instance cần truy cập. Nếu dùng `jcmd -l` hay `VirtualMachine.list()`, coi đó là **danh sách ứng viên** để đối chiếu thêm.

**Bước 3 — Kiểm tra process ở tầng OS.** Với ID dạng PID, dùng `ProcessHandle.of(pid)` để kiểm tra `isAlive()`, `info().startInstant()`, `info().user()` và `info().commandLine()` nếu OS cho phép. Nếu dữ liệu cần thiết không có, **không tự suy đoán**; hãy dùng nguồn kiểm chứng khác đáng tin hoặc dừng.

**Bước 4 — Đối chiếu descriptor.** Tìm ID tương ứng trong `VirtualMachine.list()`. Nếu không có, hoặc có nhiều descriptor không thể phân biệt, không chọn bừa. `displayName` chỉ là dấu hiệu bổ sung.

**Bước 5 — Kiểm tra lại ngay trước attach.** Đảm bảo PID còn sống, start time không thay đổi, user/command vẫn phù hợp. Nếu khác lần trước, dừng và xác định lại từ đầu.

**Bước 6 — Gọi `VirtualMachine.attach(descriptor)`.** Khi đã có descriptor đúng provider, overload này giữ lựa chọn provider thay vì thử dò qua các provider theo chuỗi ID.

**Bước 7 — Xác nhận sau attach trước khi làm tác vụ nhạy cảm.** Kiểm tra lại danh tính OS và, nếu ứng dụng có cơ chế nhận diện, so một marker/thuộc tính của đúng target. Nếu không khớp thì từ chối bước kế tiếp.

**Bước 8 — `detach()` trong `finally`.** Dù kiểm tra hoặc thao tác ném exception, vẫn cố gắng đóng kết nối. `detach()` không làm JVM mục tiêu kết thúc; nếu trước đó đã nạp agent thì detach cũng **không tự gỡ agent**.

Trình tự này giảm sai sót vận hành, nhưng không biến PID hay marker thành cơ chế xác thực mật mã. Kiểm soát quyền attach vẫn do hệ điều hành/JVM và chính sách triển khai quyết định.

## 5. Điều kiện trước khi làm thí nghiệm

Thí nghiệm bên dưới sử dụng **JDK 17 trở lên**, với JDK HotSpot/OpenJDK thông dụng có module `jdk.attach`. Hai chương trình Java chạy riêng biệt trên **cùng máy và cùng người dùng hệ điều hành**. Đảm bảo:

- `java -version` và `javac -version` trỏ tới JDK phù hợp; không sử dụng runtime image tùy biến đã bỏ `jdk.attach`.
- JVM mục tiêu cho phép attach. Ví dụ chạy **không** có `-XX:+DisableAttachMechanism`.
- Có quyền truy cập process và thông tin `ProcessHandle.Info` cần dùng. Một số OS, container hoặc chính sách quyền có thể ẩn `startInstant`, user hoặc command line.
- Dùng đúng PID **mà JVM mục tiêu tự in**. Trong thí nghiệm, provider của HotSpot ánh xạ ID tới PID tại cùng PID namespace.
- Không thử self-attach vào chính JVM của công cụ; chương trình verifier và target chạy ở hai process khác nhau.
- Một process có thể thoát bất kỳ lúc nào. Không nên xem kết quả kiểm tra trước attach là sự đảm bảo vĩnh viễn.

Đây là thí nghiệm về **định danh và kết nối**. Chương trình verifier chỉ đọc property `attach.demo.id` sau attach; nó không tải agent, không yêu cầu mở JMX và không sửa class.

## 6. Ví dụ Java 17+: tạo một JVM mục tiêu có dấu hiệu nhận diện

Tạo file **`AttachTarget.java`**:

```java
import java.time.Instant;

public final class AttachTarget {
    public static void main(String[] args) throws InterruptedException {
        String marker = System.getProperty("attach.demo.id");
        if (marker == null || marker.isBlank()) {
            throw new IllegalStateException(
                    "Missing -Dattach.demo.id system property");
        }

        ProcessHandle self = ProcessHandle.current();
        Instant started = self.info().startInstant()
                .orElseThrow(() -> new IllegalStateException(
                        "OS process start time is unavailable"));

        System.out.println("PID=" + self.pid());
        System.out.println("START=" + started);
        System.out.println("MARKER=" + marker);
        System.out.flush();

        // Giữ process chạy để verifier kết nối từ terminal khác.
        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Điều cần quan sát:

- `ProcessHandle.current().pid()` trả PID **của chính JVM mục tiêu**, không phải PID của verifier.
- `startInstant()` trả thời điểm OS ghi nhận process được khởi tạo nếu thông tin khả dụng.
- `-Dattach.demo.id=...` đặt một Java system property trước `main`. Ví dụ dùng marker dễ nhận biết, **không phải secret**.
- `while (true)` chỉ giữ JVM sống đủ lâu để luyện thao tác; kết thúc bằng `Ctrl+C` khi xong.

## 7. Ví dụ Java 17+: verifier kiểm tra ID rồi attach

Tạo file **`VerifiedAttach.java`**:

```java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import java.time.Instant;
import java.util.List;
import java.util.Properties;

public final class VerifiedAttach {

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: VerifiedAttach <PID> <START> <MARKER>");
            System.exit(2);
        }

        String suppliedId = args[0];
        long pid = Long.parseLong(suppliedId);
        Instant expectedStart = Instant.parse(args[1]);
        String expectedMarker = args[2];

        if (pid <= 0 || !suppliedId.equals(Long.toString(pid))
                || expectedMarker.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid PID or marker");
        }

        // Kiểm tra bằng chứng từ OS trước khi chọn JVM.
        verifyProcess(pid, expectedStart);

        List<VirtualMachineDescriptor> matches = VirtualMachine.list()
                .stream()
                .filter(d -> suppliedId.equals(d.id()))
                .toList();

        if (matches.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one attach descriptor for PID");
        }

        VirtualMachineDescriptor descriptor = matches.get(0);
        if (!descriptor.displayName().contains("AttachTarget")) {
            throw new IllegalStateException(
                    "Unexpected JVM display name");
        }

        // Recheck ngay trước thao tác kết nối.
        verifyProcess(pid, expectedStart);

        VirtualMachine vm = VirtualMachine.attach(descriptor);
        try {
            // Không gọi loadAgent hay tác vụ thay đổi JVM trước khi xác minh.
            verifyProcess(pid, expectedStart);
            Properties properties = vm.getSystemProperties();

            if (!expectedMarker.equals(
                    properties.getProperty("attach.demo.id"))) {
                throw new IllegalStateException(
                        "Target marker does not match");
            }

            // Một lần kiểm tra cuối để phát hiện thay PID/process.
            verifyProcess(pid, expectedStart);

            System.out.println("IDENTITY=VERIFIED");
            System.out.println("ATTACH=READ_ONLY_SUCCESS");
        } finally {
            vm.detach();
        }
    }

    private static void verifyProcess(long pid, Instant expectedStart) {
        ProcessHandle process = ProcessHandle.of(pid)
                .orElseThrow(() -> new IllegalStateException(
                        "Target PID no longer exists"));

        if (!process.isAlive()) {
            throw new IllegalStateException("Target is not alive");
        }

        ProcessHandle.Info info = process.info();

        Instant currentStart = info.startInstant()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target start time"));
        if (!currentStart.equals(expectedStart)) {
            throw new IllegalStateException(
                    "PID was reused or start time differs");
        }

        String targetUser = info.user()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target OS user"));
        String ownUser = ProcessHandle.current().info().user()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify verifier OS user"));
        if (!targetUser.equals(ownUser)) {
            throw new IllegalStateException(
                    "Target is owned by a different OS user");
        }

        String commandLine = info.commandLine()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target command line"));
        if (!commandLine.contains("AttachTarget")) {
            throw new IllegalStateException(
                    "Target command line does not match");
        }
    }
}
```

### Vì sao đoạn mã cố ý “khó tính”?

- `args[0]` phải là chuỗi PID dạng thập phân chuẩn trong môi trường demo, không chấp nhận `000123` như một cách tự đoán ID.
- `Instant.parse(args[1])` sử dụng **chính thời điểm** mục tiêu đã in, thay vì phỏng đoán từ giờ chạy chương trình.
- `verifyProcess(...)` thất bại ngay nếu mất dữ liệu quan trọng, thay vì coi `Optional.empty()` là “có vẻ đúng”.
- `matches.size() != 1` từ chối descriptor không rõ hoặc không duy nhất. `VirtualMachine.list()` có thể biến động theo thời gian.
- `displayName.contains("AttachTarget")` là một lớp kiểm tra bổ sung hợp với **lệnh chạy ví dụ**. Trong ứng dụng thực không nên coi tên hiển thị là danh tính đáng tin.
- `VirtualMachine.attach(descriptor)` chọn chính provider thuộc descriptor vừa đối chiếu. Overload `attach(String)` cũng hợp lệ khi ID được xác định cho đúng provider/môi trường, nhưng cần cùng chính sách xác nhận.
- Việc đọc marker xảy ra **sau attach nhưng trước mọi tác vụ có thể tác động tới JVM**. Trong demo, nó chỉ chứng minh target có property mong đợi; không được dùng như cơ chế ủy quyền an toàn.
- `finally` đảm bảo `vm.detach()` được gọi nếu kết nối attach thành công, kể cả khi property không trùng hoặc thao tác đọc lỗi.

Lưu ý: mã biên dịch được với Java 17+, nhưng attach thành công còn phụ thuộc hệ điều hành, JDK, quyền process, attach provider và dữ liệu `ProcessHandle.Info`. Việc **từ chối thao tác khi không đủ bằng chứng** là hành vi có chủ ý.

## 8. Biên dịch và chạy trong hai terminal

Trong cùng thư mục chứa `AttachTarget.java` và `VerifiedAttach.java`, mở terminal 1 và biên dịch:

```powershell
javac --add-modules jdk.attach -encoding UTF-8 AttachTarget.java VerifiedAttach.java
```

Lệnh này yêu cầu compiler resolve `jdk.attach`, nơi cung cấp các lớp `VirtualMachine`/`VirtualMachineDescriptor`.

**Terminal 1 — chạy JVM mục tiêu:**

```powershell
java -Dattach.demo.id=lab-alpha AttachTarget
```

Target in ba dòng dạng:

```text
PID=...       (số PID thực do OS cấp)
START=...     (Instant thực theo định dạng ISO-8601)
MARKER=lab-alpha
```

Hai dòng đầu là **giá trị động**, nên không có stdout cố định cho toàn bộ target. Sao chép nguyên giá trị sau `PID=` và `START=`. Giữ terminal 1 đang chạy.

**Terminal 2 — nhập đúng hai giá trị vừa nhận và thực hiện attach:**

```powershell
$verifiedPid = Read-Host "PID do AttachTarget in"
$verifiedStart = Read-Host "START do AttachTarget in"
java --add-modules jdk.attach VerifiedAttach $verifiedPid $verifiedStart lab-alpha
```

**Stdout của verifier khi mọi kiểm tra thành công:**

```text
IDENTITY=VERIFIED
ATTACH=READ_ONLY_SUCCESS
```

Các dòng này chỉ xuất hiện sau khi OS identity, descriptor, target property và lần recheck cuối đều thành công.

Khi hoàn tất, nhấn `Ctrl+C` tại terminal 1 để dừng `AttachTarget`. Bản thân `vm.detach()` chỉ đóng kênh kết nối quản trị; nó không kết thúc JVM mục tiêu.

### Nếu dùng Bash trên Linux/macOS

Bước biên dịch/khởi động Java giữ nguyên. Ở terminal kiểm tra, có thể nhập:

```bash
read -r -p "PID do AttachTarget in: " verified_pid
read -r -p "START do AttachTarget in: " verified_start
java --add-modules jdk.attach VerifiedAttach \
    "$verified_pid" "$verified_start" lab-alpha
```

Ở cả hai hệ điều hành, phải chạy target và verifier trong ngữ cảnh tương thích về PID namespace và quyền attach.

## 9. Đọc luồng chương trình: xác minh trước và sau attach

### Trước attach

```java
verifyProcess(pid, expectedStart);
```

Đây là kiểm tra **OS process**, dùng `ProcessHandle`. Nó không phải một lời gọi Attach API, cũng không cần kết nối tới target JVM. Nó đối chiếu thông tin được ghi nhận từ instance cần tìm với process hiện có.

Tiếp theo:

```java
List<VirtualMachineDescriptor> matches = VirtualMachine.list()
        .stream()
        .filter(d -> suppliedId.equals(d.id()))
        .toList();
```

Đây là kiểm tra **JVM/provider**. Một PID có thể tồn tại nhưng không phải JVM attachable; `ProcessHandle` không chứng minh nó hỗ trợ Attach API. Ngược lại, một descriptor hợp lệ chưa chứng minh đó là instance được phép thao tác.

Sau đó:

```java
VirtualMachine vm = VirtualMachine.attach(descriptor);
```

Đến đây công cụ mới yêu cầu provider kết nối. Việc kiểm tra bằng OS và provider ở hai bước trước là để giảm xác suất chọn sai JVM; nó không loại bỏ hoàn toàn khả năng target thay đổi giữa các bước.

### Sau attach

```java
Properties props = vm.getSystemProperties();
String marker = props.getProperty("attach.demo.id");
```

Thao tác này **đọc thông tin hiện tại của target**, không đọc `System.getProperties()` của verifier. Đặt marker ở target giúp ta so với giá trị đã biết từ nguồn bên ngoài.

Chỉ khi marker đúng và process identity vẫn ổn định, verifier mới báo `IDENTITY=VERIFIED`. Trong một công cụ thực, đây là vị trí có thể quyết định **có tiếp tục một tác vụ riêng đã được cấp phép hay không**. Nên tách phần xác minh khỏi phần thực thi để tránh dùng nhầm target hoặc trộn lẫn quyền hạn.

### Vì sao phải kiểm tra nhiều lần?

Hãy hình dung target thoát giữa hai thao tác:

```text
10:00:00.000  đọc PID 3180, start=T1
10:00:00.100  JVM A thoát
10:00:00.200  JVM B được OS cấp PID 3180, start=T2
10:00:00.300  attach bằng chuỗi "3180"
```

Nếu không kiểm tra lại, thao tác có thể nhắm B. Việc so `startInstant` giúp phát hiện T2 khác T1. Sau attach, đọc marker thêm một lớp xác minh. Tuy nhiên **không có giao dịch nguyên tử giữa API xem OS process và Attach API**; nếu yêu cầu mức bảo đảm cao hơn, phải dùng cơ chế nhận diện/cấp quyền của hệ thống quản lý process và thiết kế tác vụ an toàn theo môi trường.

## 10. `list()`, `attach(String)` và `attach(descriptor)` chọn thế nào?

| Cách | Điểm mạnh | Điều phải kiểm tra |
| --- | --- | --- |
| `VirtualMachine.list()` | Khám phá ứng viên và provider/ID; hữu ích cho công cụ tương tác | Danh sách có thể không đầy đủ, đổi theo thời gian; tên và ID chưa chắc đủ xác nhận |
| `VirtualMachine.attach(id)` | Thuận tiện khi định danh theo provider đã được kiểm chứng | Với nhiều provider, API lần lượt thử provider; cần biết rõ định danh dùng được trong môi trường nào |
| `VirtualMachine.attach(descriptor)` | Gắn đúng provider đã tạo descriptor | Descriptor vẫn là snapshot; target có thể đã thoát, bị thay hoặc từ chối attach |

Trong demo, đã chọn descriptor từ `list()` bằng một ID đã được kiểm tra ở OS nên dùng overload theo descriptor là lựa chọn dễ giải thích. Khi chạy trong một hệ thống nơi provider không dùng PID, không thể tái sử dụng nguyên xi bước `Long.parseLong(id)`/`ProcessHandle.of(pid)`; cần mô hình xác thực phù hợp provider đó.

Cũng không nên tự sinh `VirtualMachineDescriptor` với một provider tùy đoán để “vượt qua” việc không tìm thấy target. Không tìm được hoặc không xác nhận được đích là kết quả cần được báo rõ.

## 11. Khi attach thất bại: đọc đúng nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| `VirtualMachine.list()` không thấy PID | JVM không được provider liệt kê, không cùng namespace, quyền hạn hoặc process đã thoát | Xác nhận PID, OS user, namespace, target còn chạy; không chọn JVM khác |
| `AttachNotSupportedException` | Provider không hỗ trợ, ID sai, target đã thoát, attach bị tắt | Kiểm tra JVM/provider, mục tiêu và JVM flags |
| `IOException` ở attach | Lỗi kênh giao tiếp, quyền file/socket, target không đáp ứng, lỗi nền tảng | Đọc đầy đủ message/cause, xem log target và quyền OS |
| `SecurityException` | Chính sách quyền của runtime/provider chặn thao tác | Xác nhận quyền được cấp, không tự động nâng quyền |
| `startInstant()`/`user()`/`commandLine()` rỗng | OS không cung cấp metadata hoặc không đủ quyền xem | Dừng quy trình mẫu; tìm nguồn định danh độc lập phù hợp |
| `PID was reused or start time differs` | PID sai hoặc đã được OS tái sử dụng | Thu lại thông tin từ instance đúng, không retry bằng PID cũ |
| `Unexpected JVM display name` | Không phải class mục tiêu demo hoặc provider mô tả khác | So lại lệnh khởi động và descriptor; không bỏ check tùy tiện |
| `Target marker does not match` | Kết nối tới JVM khác, sai lần chạy hoặc marker đã đổi | Detach và xác minh instance mới trước khi tiếp tục |
| `NoClassDefFoundError` / module không có | JDK/runtime image thiếu `jdk.attach` hoặc cấu hình module không đúng | Kiểm tra bản phân phối JDK và `--add-modules jdk.attach` |
| JVM khác namespace PID | PID nhìn từ host khác với PID nhìn trong container | Thực hiện attach từ ngữ cảnh thích hợp, đồng nhất namespace và định danh |

Với HotSpot, tùy cấu hình JVM có thể sử dụng flag `-XX:+DisableAttachMechanism` để từ chối cơ chế attach. Đừng giải quyết lỗi bằng cách vô hiệu hóa kiểm tra danh tính hoặc cố gắng attach một JVM khác chỉ vì nó “gần giống”.

### Phân biệt lỗi attach với cảnh báo nạp agent động

Từ JDK 21 (JEP 451), **nạp Java agent/JVMTI agent vào JVM đang chạy** có các cảnh báo/chính sách riêng nhằm chuẩn bị cho việc giới hạn dynamic loading. Gọi `VirtualMachine.attach(...)` rồi **chỉ** `getSystemProperties()` như bài thực hành này **không phải** thao tác tải agent. Tránh suy ra rằng một cảnh báo liên quan `loadAgent` đồng nghĩa mọi thao tác attach đều thất bại, hoặc rằng chỉ cần thêm một VM flag là đã có quyền đối với target.

Nếu bài toán sau này cần `loadAgent`, phải xem phiên bản JDK đang dùng, cơ chế cho phép của target và quyền vận hành. Nội dung đó là một bước riêng sau xác minh danh tính.

## 12. Quy tắc an toàn và tính tin cậy khi xây tool thật

1. **Không nhận một PID không được xác minh rồi lập tức attach.** Bắt đầu bằng record của đúng instance, không chọn ngẫu nhiên phần tử đầu trong `VirtualMachine.list()`.
2. **Không coi displayName, main class hoặc JAR name là duy nhất.** Nhiều môi trường/service có thể dùng cùng class.
3. **Không coi marker demo là secret hoặc chứng thực.** Bất kỳ đối tượng nào có quyền quan sát command line hoặc thay system property có thể biết/chỉnh marker; cần cơ chế ủy quyền độc lập nếu bài toán nhạy cảm.
4. **Không ghi log toàn bộ `getSystemProperties()`.** Target properties có thể chứa thông tin cấu hình hoặc dữ liệu nhạy cảm. Chỉ đọc và xử lý trường cần thiết.
5. **Không tin thông tin cache quá lâu.** PID và descriptor là ảnh chụp tại thời điểm đọc; hãy kiểm tra lại trước khi thực hiện thao tác.
6. **Không tự động nâng quyền để attach.** Chỉ sử dụng quyền process đã được cấp, đúng user và đúng môi trường.
7. **Giới hạn thời gian và xử lý lỗi rõ ràng.** Attach có thể chậm, target có thể bận hoặc dừng; một tool điều phối nên có timeout ở tầng điều khiển và thông báo nguyên nhân.
8. **Luôn có chiến lược detach.** `finally` phù hợp khi `attach()` trả về thành công; nếu `detach()` gây `IOException`, cũng cần báo lỗi và không giả vờ thao tác đã đóng sạch.
9. **Không nhầm attach thành trạng thái vĩnh viễn.** Connection là phiên điều khiển; JVM vẫn chạy sau detach, và thay đổi trước đó (nếu có) không tự đảo ngược.
10. **Kiểm tra trên môi trường triển khai thật.** HotSpot, OpenJ9, container, OS và JDK version có thể khác nhau về provider, quyền, dữ liệu process và cơ chế agent.

## 13. Tình huống tự luyện

### Tình huống A — hai JVM cùng chạy một main class

Cả A và B đều là `AttachTarget`, chỉ khác PID, `START` và marker. Công cụ lọc `displayName.contains("AttachTarget")` sẽ tìm thấy cả hai.

**Cách làm:** dùng PID được mục tiêu chính xác công bố, đối chiếu start time và OS user, chọn descriptor theo ID và kiểm tra marker của đúng lần chạy. Nếu thiếu bằng chứng, dừng.

### Tình huống B — PID đúng hôm qua nhưng hôm nay khác process

Record cũ có `(PID=3180, START=T1)`, process mới có `(PID=3180, START=T2)`.

**Kết quả:** `verifyProcess` báo sai start time. Không gọi attach bằng ID cũ. Hãy lấy record của instance mới và xác nhận nó thực sự là mục tiêu cần thao tác.

### Tình huống C — đã attach, marker sai

Kết nối được thiết lập, `getSystemProperties()` trả marker không khớp.

**Kết quả:** verifier ném exception, `finally` gọi `detach`. Không gọi tác vụ thay đổi target. Đây là lý do việc kiểm tra sau attach phải đi **trước** những bước có ảnh hưởng.

### Tình huống D — `list()` không trả descriptor nhưng process còn sống

`ProcessHandle.of(pid).isAlive()` là true, nhưng không có descriptor tương ứng.

**Kết luận:** Có process sống không đồng nghĩa đó là JVM attachable trong phạm vi provider. Cần xác minh cấu hình, quyền và namespace; không tự thay ID hoặc lấy một JVM khác.

### Tình huống E — chỉ có PID, không có start time

`ProcessHandle.Info.startInstant()` rỗng vì chính sách OS.

**Kết luận:** Quy trình mẫu từ chối tiếp tục. Trong tool thật cần nguồn danh tính đáng tin khác, ví dụ record từ supervisor với thời điểm khởi chạy/instance ID, hoặc chấp nhận rõ một mức đảm bảo khác theo chính sách đã định; không tự biến “không có dữ liệu” thành “đã xác minh”.

## 14. Câu hỏi kiểm tra hiểu bài

**1. `VirtualMachineDescriptor.id()` có luôn luôn là PID?**  
Không. API chỉ bảo đảm nó là định danh của provider; trên nhiều JVM/OS nó thường là PID.

**2. Có thể attach chỉ bằng `displayName` không?**  
Không có API đảm bảo tính duy nhất của displayName. Nó dành cho hiển thị, cần đối chiếu ID và thông tin target khác.

**3. Vì sao phải ghi lại `startInstant` ngoài PID?**  
Vì OS có thể tái sử dụng PID, nên start time giúp phát hiện đúng PID nhưng sai vòng đời process.

**4. `VirtualMachine.attach(...)` có lập tức chạy `agentmain` hay chèn bytecode không?**  
Không. Đó là thao tác thiết lập kết nối. Chỉ khi thực hiện một thao tác nạp agent phù hợp thì agent mới được yêu cầu chạy theo cơ chế của nó.

**5. Sau `vm.getSystemProperties()` có thể in mọi property để debug không?**  
Không nên. Properties có thể có dữ liệu nhạy cảm; chỉ kiểm tra những khóa cần thiết.

**6. `vm.detach()` có dừng JVM hoặc gỡ agent đã nạp không?**  
Không. Nó chỉ ngắt kết nối attach của công cụ.

**7. Nếu marker đúng thì có thể coi đó là xác thực bảo mật không?**  
Không. Marker là một bằng chứng đối chiếu trong bài lab, không phải credential và không thay thế cơ chế phân quyền của hệ thống.

**8. Lý do dùng `attach(descriptor)` thay vì `attach(id)` trong ví dụ?**  
Descriptor giữ tham chiếu tới provider đã liệt kê JVM ứng viên; cách này bám sát cặp provider/ID vừa được đối chiếu. Vẫn cần kiểm tra lifecycle và target vì descriptor có thể cũ.

## 15. Tài liệu chính thức để đối chiếu

- [JDK 21 — `VirtualMachine`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `list`, `attach`, `getSystemProperties`, `detach`, các thao tác nạp agent.
- [JDK 21 — `VirtualMachineDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachineDescriptor.html): `id`, `displayName`, `provider`, tính phụ thuộc implementation của định danh.
- [JDK 21 — `ProcessHandle.Info`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): `startInstant`, `user`, `commandLine`, và tính tùy chọn của process metadata.
- [OpenJDK — JEP 451](https://openjdk.org/jeps/451): cảnh báo/chính sách về việc nạp agent động, phân biệt với kết nối attach chỉ đọc.

**Điểm cần nhớ:** Một JVM “attach được” chưa chắc là **đúng JVM**. Hãy dùng `VirtualMachine.attach(...)` sau khi đã đối chiếu ID với bằng chứng của đúng instance, kiểm tra lại trước/sau kết nối, chỉ thực hiện thao tác được phép và luôn `detach()` khi hoàn thành.