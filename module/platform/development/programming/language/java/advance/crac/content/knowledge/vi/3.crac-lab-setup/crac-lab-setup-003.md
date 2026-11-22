# Kiểm tra khả năng hỗ trợ CRaC của bản dựng đang sử dụng

Trước khi thiết kế hoặc chạy một ứng dụng bằng CRaC (Coordinated Restore at Checkpoint), cần xác định chính xác bản JDK nào đang được dùng và bản dựng đó hỗ trợ đến đâu. Một dự án có thể biên dịch thành công với API CRaC nhưng lại chạy bằng JVM thông thường; máy phát triển có thể dùng JDK hỗ trợ CRaC trong khi Gradle daemon hoặc container triển khai lại dùng một JDK khác.

Vì vậy, kết quả kiểm tra cần trả lời được bốn câu hỏi:

1. Công cụ build và trình biên dịch đang dùng JDK nào?
2. JVM thực sự chạy ứng dụng có nhận các tùy chọn CRaC hay không?
3. Công cụ điều khiển JVM có cung cấp lệnh checkpoint hay không?
4. Hệ điều hành, CRIU và môi trường triển khai có thể thực hiện checkpoint/restore thực tế hay không?

Không nên kết luận chỉ từ tên nhà cung cấp hoặc chuỗi phiên bản Java. Một phép kiểm tra tùy chọn JVM có thể xác nhận runtime nhận biết CRaC, nhưng chỉ một lần checkpoint và restore thành công trong môi trường đích mới xác nhận được toàn bộ đường chạy.

## 1. Phân biệt các lớp cần kiểm tra

CRaC liên quan đến nhiều thành phần. Mỗi phép kiểm tra chỉ chứng minh một phần khả năng hỗ trợ.

| Lớp | Cần xác định | Bằng chứng phù hợp |
| --- | --- | --- |
| API lúc biên dịch | Dự án có thể tham chiếu các kiểu như `org.crac.Resource` hay không | Build biên dịch thành công với dependency API CRaC |
| JVM lúc chạy | JVM có nhận biết tùy chọn và cơ chế CRaC hay không | Tùy chọn `-XX:CRaCCheckpointTo` được chấp nhận; bản dựng JDK được xác định rõ |
| Công cụ điều khiển | Có thể yêu cầu JVM checkpoint bằng công cụ đi kèm hay không | `jcmd` kết nối được tới đúng tiến trình và liệt kê lệnh `JDK.checkpoint` |
| Môi trường hệ điều hành | Cơ chế checkpoint/restore có hoạt động trên máy hoặc container đích hay không | CRIU và kernel đáp ứng điều kiện; thử nghiệm checkpoint rồi restore thành công |
| Ứng dụng | Tài nguyên và trạng thái ứng dụng có thể đi qua hai mốc checkpoint/restore hay không | Callback chạy đúng, tài nguyên được kết nối lại và ứng dụng đạt readiness |

Các lớp này có quan hệ với nhau nhưng không thể thay thế bằng chứng cho nhau. Có dependency API không chứng minh JVM hỗ trợ checkpoint. JVM nhận tùy chọn cũng chưa chứng minh CRIU có đủ quyền để ghi ảnh tiến trình. Một ảnh được tạo thành công vẫn chưa chứng minh ứng dụng đã kết nối lại đúng các dịch vụ bên ngoài.

## 2. Xác định đúng JDK đang được sử dụng

Trước tiên, hãy ghi lại đường dẫn và thông tin của Java executable mà lệnh hiện tại tìm thấy. Không chỉ ghi lại phiên bản; cần biết chính xác executable đến từ thư mục nào.

### 2.1. Kiểm tra trên Windows PowerShell

Chạy các lệnh sau trong cùng terminal mà bạn dùng để build hoặc chạy ứng dụng:

```powershell
# Tất cả vị trí java tìm thấy trên PATH
Get-Command java -All | Select-Object Source
where.exe java

# JDK mà lệnh java hiện tại thực sự chạy
java -version
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|java.vendor|java.runtime.version|os.name|os.arch'

# Biến môi trường, nếu được cấu hình
$env:JAVA_HOME

# Kiểm tra các công cụ đi kèm JDK
javac -version
jcmd -l
```

Các thông tin cần lưu lại gồm:

- Đường dẫn `java.exe` được tìm thấy đầu tiên trên `PATH`.
- `java.home`, `java.vendor` và `java.runtime.version`.
- Phiên bản `javac` và khả năng gọi `jcmd`.
- Hệ điều hành và kiến trúc CPU.

`JAVA_HOME` chỉ là một biến môi trường. Nếu `PATH` trỏ tới một thư mục Java khác, lệnh `java` vẫn có thể chạy executable khác với thư mục được khai báo trong `JAVA_HOME`. Vì vậy, cần đối chiếu cả đường dẫn lẫn thuộc tính runtime.

### 2.2. Kiểm tra trên Linux

```bash
# Đường dẫn Java được shell tìm thấy
command -v java
which -a java
readlink -f "$(command -v java)"

# Thông tin runtime và môi trường
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|java.vendor|java.runtime.version|os.name|os.arch'

# Biến môi trường và công cụ JDK
echo "$JAVA_HOME"
javac -version
jcmd -l
```

Nếu có nhiều JDK cài trên máy, hãy chạy lệnh bằng đường dẫn tuyệt đối để tránh nhầm lẫn:

```bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/jcmd" -l
```

Đường dẫn tuyệt đối giúp xác nhận các công cụ được lấy từ cùng một JDK. Khi kiểm tra một tiến trình đang chạy, cũng cần dùng `jcmd` tương ứng với JDK của tiến trình đó và tài khoản có quyền attach phù hợp.

### 2.3. Kiểm tra JDK của Gradle và JDK chạy ứng dụng

Lệnh `java -version` trong terminal chỉ cho biết Java mà shell tìm thấy. Nó chưa chắc là Java mà Gradle, IDE, container hoặc dịch vụ triển khai đang sử dụng.

Với dự án Gradle, chạy:

```bash
./gradlew --version
```

Trên Windows:

```powershell
.\gradlew.bat --version
```

Đọc phần JVM trong kết quả để xác định JDK dùng cho Gradle. Nếu dự án khai báo Java Toolchain, trình biên dịch có thể dùng một JDK khác với JVM chạy Gradle. Khi dự án áp dụng Java plugin, có thể xem các toolchain Gradle phát hiện bằng:

```bash
./gradlew javaToolchains
```

Khi cần xác nhận compiler được chọn cho một tác vụ cụ thể, xem log của tác vụ biên dịch ở chế độ thông tin:

```bash
./gradlew compileJava --info
```

JDK chạy ứng dụng phải được kiểm tra riêng. Nếu ứng dụng chạy trong container, hãy thực hiện `java -version` và kiểm tra đường dẫn Java ngay bên trong container đang chạy. JDK trên máy host không chứng minh image triển khai có cùng runtime.

Hãy phân biệt ít nhất ba giá trị:

| Vị trí | Câu hỏi cần trả lời |
| --- | --- |
| Gradle daemon hoặc Maven process | Công cụ build đang chạy trên JDK nào? |
| Java compiler/toolchain | Mã nguồn được biên dịch bằng JDK nào? |
| Runtime thực tế | JAR hoặc ứng dụng được chạy bằng JVM nào trong môi trường đích? |

Nếu các giá trị khác nhau, hãy kiểm tra CRaC trên đúng runtime thực tế. Một kết quả tốt từ JDK trên máy lập trình không thể đại diện cho JDK trong container sản xuất.

## 3. Kiểm tra API CRaC ở bước biên dịch

API CRaC cung cấp các kiểu để ứng dụng đăng ký resource và nhận callback trước checkpoint, sau restore. Các kiểu thường dùng nằm trong package `org.crac`, ví dụ:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
```

Trong dự án dùng Gradle, API có thể được khai báo bằng dependency `org.crac:crac` theo phiên bản mà dự án quản lý:

```groovy
dependencies {
    implementation("org.crac:crac:$cracApiVersion")
}
```

`cracApiVersion` trong ví dụ là giá trị cần được khai báo trong version catalog, convention hoặc cấu hình dependency của dự án. Hãy dùng phiên bản tương thích với JDK và thư viện đang triển khai.

Sau khi dependency được cấu hình, có thể chạy tác vụ biên dịch Java của dự án để xác nhận compiler tìm thấy API:

```bash
./gradlew compileJava
```

Nếu mã nguồn tham chiếu `org.crac` và build biên dịch thành công, điều đó chứng minh classpath biên dịch có API cần thiết. Kết quả này **không chứng minh JVM lúc chạy hỗ trợ CRaC**. Dependency API có thể cho phép mã nguồn biên dịch trên một JDK thông thường; đến lúc chạy, JVM vẫn có thể không nhận tùy chọn checkpoint.

Vì vậy, cần ghi riêng hai kết quả: `API_COMPILE=PASS/FAIL` và `JVM_CRAC=PASS/FAIL`. Không gộp chúng thành một kết luận duy nhất.

## 4. Kiểm tra JVM có nhận tùy chọn CRaC

Các bản JDK có tích hợp CRaC thường cung cấp tùy chọn chỉ định thư mục checkpoint và tùy chọn restore. Tên thường gặp là:

- `-XX:CRaCCheckpointTo=<directory>`: chỉ định nơi lưu checkpoint khi yêu cầu checkpoint được thực hiện.
- `-XX:CRaCRestoreFrom=<directory>`: khởi chạy tiến trình bằng cách restore từ checkpoint đã có.

Tên tùy chọn và cách sử dụng cần được đối chiếu với tài liệu của đúng bản phân phối JDK. Phép thử dưới đây chỉ kiểm tra JVM có nhận tùy chọn checkpoint hay không; nó không tạo checkpoint và không xác nhận CRIU hoạt động.

### 4.1. Thử nhận diện tùy chọn trên Windows

```powershell
$checkpointDir = Join-Path $env:TEMP 'crac-flag-probe'
java "-XX:CRaCCheckpointTo=$checkpointDir" -version
$LASTEXITCODE
```

Nếu JVM nhận tùy chọn, lệnh thường in thông tin phiên bản và trả mã thoát `0`. Nếu JVM báo `Unrecognized VM option` hoặc thông báo tương tự, executable đang được gọi không nhận tùy chọn đó. Hãy kiểm tra lại đường dẫn `java.exe`, nhà cung cấp JDK và bản dựng CRaC được cài đặt.

### 4.2. Thử nhận diện tùy chọn trên Linux

```bash
java -XX:CRaCCheckpointTo=/tmp/crac-flag-probe -version
echo $?
```

Mã thoát `0` cùng thông tin phiên bản cho biết JVM đã chấp nhận tùy chọn trong phép thử này. Nếu cần loại bỏ sự mơ hồ về `PATH`, hãy thay `java` bằng đường dẫn tuyệt đối tới executable đã xác định ở bước trước.

Không dùng tùy chọn restore với một thư mục chưa có checkpoint để kiểm tra nhận diện. JVM có thể cố gắng restore và báo lỗi do ảnh chưa tồn tại; kết quả đó không phải phép thử phù hợp cho khả năng nhận tùy chọn.

### 4.3. Diễn giải đúng kết quả

| Kết quả | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| JVM báo tùy chọn không được nhận diện | Executable đang kiểm tra không cung cấp tùy chọn đó | Chưa biết liệu một JDK khác trên máy có hỗ trợ hay không |
| JVM nhận tùy chọn và in phiên bản | Bản JVM đó nhận biết tùy chọn checkpoint | Chưa xác nhận checkpoint thực tế, CRIU, quyền hệ điều hành hoặc callback ứng dụng |
| JVM báo CRaC không được hỗ trợ trên nền tảng hiện tại | Bản dựng hoặc nền tảng hiện tại không thể thực hiện đường chạy được yêu cầu | Chưa loại trừ khả năng dùng JDK đó trong một môi trường Linux tương thích khác |
| Phép thử chạy trên host thành công | Runtime trên host nhận tùy chọn | Chưa chứng minh runtime bên trong container hoặc máy đích giống hệt |

Không nên suy luận chỉ từ chuỗi phiên bản như `21.x`, `17.x` hoặc tên nhà cung cấp. Một số nhà cung cấp có nhiều biến thể JDK khác nhau; khả năng CRaC phụ thuộc bản phân phối, phiên bản và nền tảng cụ thể.

## 5. Kiểm tra lệnh checkpoint trong jcmd

`jcmd` là công cụ chẩn đoán đi kèm JDK, có thể gửi lệnh quản trị tới một JVM đang chạy. Với các bản JDK CRaC hỗ trợ giao diện này, lệnh checkpoint thường có tên `JDK.checkpoint`.

Trước tiên, khởi chạy một tiến trình Java thử nghiệm bằng đúng JDK cần kiểm tra. Sau đó liệt kê tiến trình:

```bash
jcmd -l
```

Lệnh này hiển thị các tiến trình Java mà công cụ có thể phát hiện. Lấy PID của tiến trình cần kiểm tra rồi yêu cầu danh sách lệnh mà JVM đó hỗ trợ:

```bash
jcmd <pid> help
```

Tìm `JDK.checkpoint` trong kết quả. Nếu có, JVM cung cấp lệnh điều khiển checkpoint qua `jcmd`. Nếu không có, hãy xác minh:

- PID có thuộc tiến trình được chạy bằng JDK CRaC dự định kiểm tra không;
- `jcmd` có đến từ cùng JDK với tiến trình không;
- tài khoản hiện tại có quyền attach vào tiến trình không;
- tiến trình có tắt cơ chế attach hoặc chạy trong môi trường hạn chế không.

Có thể xem thêm thông tin của JVM đích bằng:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
```

Hai lệnh này giúp xác định bản JVM và tham số khởi chạy của tiến trình thực tế. Trên Windows, dùng `jcmd.exe` trong thư mục `bin` của JDK đang kiểm tra và truyền PID theo cùng cách.

Việc `jcmd` có lệnh `JDK.checkpoint` là bằng chứng mạnh hơn việc chỉ nhận diện một cờ JVM, nhưng vẫn chưa chứng minh thao tác checkpoint thành công. Cần thử trong môi trường có backend checkpoint/restore tương thích.

## 6. Kiểm tra CRIU và môi trường Linux

Trong cách triển khai CRaC phổ biến trên Linux, CRIU (Checkpoint/Restore In Userspace) thực hiện phần ghi và phục hồi trạng thái tiến trình ở cấp hệ điều hành. JVM có thể nhận tùy chọn CRaC nhưng checkpoint vẫn thất bại nếu CRIU thiếu, kernel không đáp ứng yêu cầu hoặc container không có quyền cần thiết.

Trên máy Linux hoặc bên trong container đích, kiểm tra:

```bash
criu --version
criu check
```

`criu --version` cho biết phiên bản công cụ. `criu check` kiểm tra một số khả năng và điều kiện môi trường mà CRIU cần. Đọc toàn bộ kết quả và mã thoát; không chỉ dựa vào việc lệnh có tồn tại.

Nếu CRIU báo thiếu quyền hoặc tính năng kernel, hãy kiểm tra cách chạy, cấu hình kernel và chính sách container. Một số môi trường container giới hạn capability, namespace hoặc thao tác với tiến trình khiến CRIU không thể hoạt động. Quyền cần thiết phụ thuộc phiên bản CRIU, kernel và cách triển khai; không nên sao chép một danh sách capability cố định sang mọi môi trường.

Ngoài CRIU, hãy xác nhận:

- Thư mục checkpoint tồn tại hoặc có thể được tạo bởi tiến trình ứng dụng.
- Tiến trình có quyền ghi vào thư mục và đủ dung lượng lưu ảnh.
- Đường dẫn checkpoint có thể truy cập trong môi trường restore.
- JDK, thư viện native, kiến trúc CPU và cấu hình hệ điều hành giữa lúc tạo ảnh và restore tương thích.
- Chính sách bảo mật và runtime container cho phép các thao tác mà CRIU cần.

CRaC và CRIU thường được triển khai trong môi trường Linux. Nếu máy phát triển là Windows hoặc macOS, việc JVM nhận một tùy chọn không có nghĩa máy host có thể thực hiện checkpoint. Hãy kiểm tra trong đúng Linux VM, WSL hoặc container sẽ chạy ứng dụng; kết quả cuối cùng phải đến từ môi trường triển khai thực tế. WSL hoặc container cũng cần đáp ứng điều kiện kernel và quyền của CRIU, không mặc nhiên được hỗ trợ chỉ vì có shell Linux.

## 7. Thực hiện smoke test checkpoint/restore

Sau các bước kiểm tra tĩnh, hãy dùng một ứng dụng thử nghiệm nhỏ để xác nhận toàn bộ đường chạy. Chỉ thực hiện trong môi trường cô lập, với dữ liệu thử nghiệm và không kết nối tới các dịch vụ nghiệp vụ thật. Mục tiêu là chứng minh JVM tạo được checkpoint, restore được tiến trình và callback của ứng dụng được gọi.

### 7.1. Tạo resource thử nghiệm

Đoạn mã sau đăng ký một resource vào global context và ghi log tại hai mốc vòng đời:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracProbe implements Resource {

    public CracProbe() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        System.out.println("CRAC_PROBE: beforeCheckpoint");
        System.out.flush();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        System.out.println("CRAC_PROBE: afterRestore");
        System.out.flush();
    }

    public static void main(String[] args) throws InterruptedException {
        new CracProbe();
        System.out.println("CRAC_PROBE: application started");
        System.out.flush();

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Đảm bảo classpath khi chạy có API CRaC tương ứng nếu bản JDK không cung cấp sẵn API đó. Đoạn mã chỉ phục vụ kiểm tra callback; nó không đại diện cho cách quản lý connection pool, consumer hoặc tài nguyên thật trong ứng dụng.

### 7.2. Khởi chạy tiến trình và tạo checkpoint

Trên Linux, ví dụ khởi chạy ứng dụng với thư mục checkpoint riêng:

```bash
mkdir -p /tmp/crac-probe-image
java -XX:CRaCCheckpointTo=/tmp/crac-probe-image \
  -cp "<classpath>" CracProbe
```

Giữ lại PID mà JVM in ra hoặc tìm tiến trình bằng `jcmd -l`. Trong terminal khác, dùng `jcmd` từ cùng JDK để yêu cầu checkpoint:

```bash
jcmd <pid> JDK.checkpoint
```

Quan sát log để xác nhận `CRAC_PROBE: beforeCheckpoint` xuất hiện và kiểm tra kết quả của thao tác checkpoint. Nếu lệnh thất bại, lưu lại toàn bộ thông báo từ JVM, `jcmd` và CRIU để xác định lớp gây lỗi.

### 7.3. Restore từ ảnh đã tạo

Khi checkpoint được tạo thành công, dùng đúng bản JDK và thư mục ảnh để restore theo cú pháp của bản phân phối đang sử dụng. Với các bản JDK hỗ trợ tùy chọn thông dụng, lệnh có dạng:

```bash
java -XX:CRaCRestoreFrom=/tmp/crac-probe-image
```

Kết quả mong đợi là tiến trình được restore, log `CRAC_PROBE: afterRestore` xuất hiện và ứng dụng tiếp tục chạy. Cú pháp, cách đóng gói classpath và hành vi tiến trình có thể phụ thuộc bản phân phối JDK; luôn đối chiếu tài liệu của runtime cụ thể.

Một smoke test đạt yêu cầu cần xác nhận đủ các điểm:

1. JVM khởi chạy được ứng dụng với tùy chọn checkpoint.
2. `jcmd` gửi được lệnh `JDK.checkpoint` tới đúng tiến trình.
3. CRIU hoàn tất việc ghi ảnh mà không báo lỗi môi trường.
4. JVM restore được ảnh bằng môi trường tương thích.
5. Callback `afterRestore` được gọi và ứng dụng tiếp tục hoạt động.

Nếu ứng dụng thật có tài nguyên bên ngoài, hãy bổ sung kiểm tra kết nối lại và readiness trong một bài thử riêng. Smoke test tối thiểu chỉ xác nhận cơ chế nền tảng, chưa xác nhận mọi resource của ứng dụng thật đều an toàn.

## 8. Đọc lỗi theo đúng lớp

Khi kiểm tra không thành công, hãy phân loại lỗi trước khi thay JDK hoặc sửa mã ứng dụng.

| Dấu hiệu | Nguyên nhân có thể | Việc cần kiểm tra tiếp |
| --- | --- | --- |
| `Unrecognized VM option` với `CRaCCheckpointTo` | Đang dùng JDK không hỗ trợ tùy chọn hoặc gọi nhầm Java executable | Kiểm tra `PATH`, `JAVA_HOME`, Gradle JVM và runtime trong container |
| API `org.crac` không tìm thấy lúc biên dịch | Thiếu dependency API hoặc cấu hình classpath sai | Kiểm tra dependency và cấu hình compiler/toolchain |
| Biên dịch thành công nhưng JVM không nhận tùy chọn | API có mặt trong classpath nhưng runtime không phải JDK CRaC phù hợp | Kiểm tra JDK dùng để chạy ứng dụng |
| `jcmd` không tìm thấy tiến trình | Dùng sai công cụ, tiến trình không được phát hiện hoặc khác tài khoản/môi trường | Dùng `jcmd` cùng JDK, kiểm tra PID và quyền attach |
| Không có `JDK.checkpoint` trong danh sách lệnh | Tiến trình không chạy trên JVM CRaC phù hợp hoặc lệnh attach không đúng JVM | Kiểm tra `VM.version`, đường dẫn `jcmd` và tài liệu JDK |
| `JDK.checkpoint` thất bại với lỗi CRIU | Thiếu hỗ trợ kernel, quyền, namespace hoặc cấu hình môi trường | Chạy `criu check` trong chính môi trường đích và xem log đầy đủ |
| Tạo ảnh được nhưng restore thất bại | Môi trường restore khác môi trường tạo ảnh hoặc ảnh không tương thích | Đối chiếu JDK, kiến trúc, kernel, thư viện native, đường dẫn và tham số chạy |
| Restore thành công nhưng callback hoặc kết nối ứng dụng lỗi | Resource hoặc trạng thái bên ngoài chưa được xử lý đúng | Kiểm tra thứ tự callback, việc đóng/mở tài nguyên và log ứng dụng |

Một lỗi trong bước checkpoint không nên được xử lý bằng cách mặc định tắt callback hoặc bỏ qua lỗi resource. Nếu một tài nguyên bắt buộc chưa ở trạng thái an toàn, ảnh tạo ra có thể không thể dùng đáng tin cậy.

## 9. Lập biên bản kết quả kiểm tra

Để người khác có thể tái hiện kết quả, hãy ghi rõ môi trường và bằng chứng. Một mẫu biên bản ngắn có thể gồm:

| Trường | Giá trị cần ghi |
| --- | --- |
| OS và kiến trúc | Tên hệ điều hành, phiên bản kernel nếu là Linux, kiến trúc CPU |
| Java executable | Đường dẫn tuyệt đối tới `java` |
| JDK vendor/version | `java.vendor`, `java.runtime.version`, `java.home` |
| Gradle/Maven JVM | Kết quả `gradlew --version` hoặc `mvn -version` |
| Java toolchain | JDK compiler được chọn cho tác vụ build |
| API compile | PASS/FAIL và dependency API được dùng |
| CRaC JVM option | PASS/FAIL, lệnh đã chạy và mã thoát |
| jcmd checkpoint command | Có/không có `JDK.checkpoint` trên đúng PID |
| CRIU | Phiên bản, kết quả `criu check` và môi trường thực hiện |
| Checkpoint | PASS/FAIL, đường dẫn ảnh và thông báo lỗi nếu có |
| Restore | PASS/FAIL, JDK dùng để restore và log callback |
| Ứng dụng | PASS/FAIL, kết quả kết nối lại và readiness nếu đã kiểm tra |

Không ghi secret, token, nội dung dữ liệu người dùng hoặc tệp checkpoint vào biên bản. Chỉ lưu thông tin cấu hình cần thiết để nhận diện môi trường và tái hiện phép thử.

## 10. Tiêu chí kết luận

Có thể phân loại kết quả theo các mức sau:

- **API_READY:** mã nguồn biên dịch được với API CRaC. Chỉ xác nhận khả năng biên dịch.
- **JVM_OPTION_READY:** JVM thực tế nhận tùy chọn checkpoint. Chỉ xác nhận runtime nhận biết tùy chọn.
- **JVM_CONTROL_READY:** `jcmd` kết nối được tới đúng JVM và có lệnh `JDK.checkpoint`.
- **PLATFORM_READY:** CRIU và môi trường hệ điều hành đáp ứng điều kiện checkpoint/restore.
- **CRAC_SMOKE_TEST_PASS:** tạo checkpoint, restore và callback đều thành công trong môi trường thử nghiệm.
- **APPLICATION_READY:** ứng dụng thật đã kiểm tra tài nguyên sau restore, kết nối lại dịch vụ và đạt readiness theo yêu cầu vận hành.

Chỉ nên tuyên bố ứng dụng đã sẵn sàng dùng CRaC khi các kiểm tra cần thiết cho runtime và nền tảng đều đạt, đồng thời các resource của ứng dụng đã được kiểm chứng. Nếu mới kiểm tra API hoặc tùy chọn JVM, hãy báo đúng mức đó và nêu rõ các bước còn thiếu.

## 11. Kết luận

Kiểm tra CRaC cần bắt đầu từ việc xác định đúng JDK của công cụ build, compiler và runtime. Sau đó xác nhận API biên dịch, tùy chọn JVM, lệnh `JDK.checkpoint`, CRIU và điều kiện của hệ điều hành. Bằng chứng cuối cùng là một smoke test tạo được checkpoint, restore được tiến trình và gọi được callback sau restore.

Kết quả chỉ có giá trị với đúng bản JDK, kiến trúc và môi trường đã kiểm tra. Khi đổi JDK, base image, kernel hoặc cấu hình container, cần kiểm tra lại trên môi trường mới trước khi phát hành ứng dụng dùng CRaC.
