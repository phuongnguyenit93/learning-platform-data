# Phân biệt JDK thông thường với bản dựng JDK có hỗ trợ CRaC

Khi bắt đầu làm việc với CRaC (Coordinated Restore at Checkpoint), một trong những việc đầu tiên cần xác định là bộ JDK đang dùng có thực sự hỗ trợ checkpoint và restore hay không. Hai bộ JDK có thể cùng dựa trên Java 17 hoặc Java 21, cùng chạy được một file JAR và cùng cung cấp các công cụ quen thuộc, nhưng khả năng của JVM bên trong có thể khác nhau.

**JDK thông thường** cung cấp môi trường phát triển và chạy Java theo các tính năng của bản phát hành tương ứng. Nếu nhà cung cấp không tích hợp CRaC vào bản dựng đó, JVM không có khả năng checkpoint và restore tiến trình theo CRaC.

**Bản dựng JDK có hỗ trợ CRaC** là một bản phân phối hoặc bản dựng JDK đã tích hợp phần hỗ trợ cần thiết ở cấp JVM để phối hợp tạo checkpoint và khôi phục tiến trình. Nó thường đi kèm hoặc được sử dụng cùng CRaC API để ứng dụng đăng ký các tài nguyên cần xử lý trước checkpoint và sau restore.

Điểm cần nhớ là tên phiên bản Java không đủ để xác định khả năng CRaC. Không thể kết luận rằng mọi JDK 17, mọi JDK 21 hoặc mọi bản OpenJDK đều có CRaC. Cần kiểm tra chính xác nhà cung cấp, bản dựng, phiên bản và môi trường chạy.

## 1. JDK thông thường là gì?

JDK (Java Development Kit) là bộ công cụ dùng để phát triển và chạy ứng dụng Java. Một bản JDK thông thường thường bao gồm:

- JVM để chạy bytecode Java.
- Trình biên dịch `javac` và các công cụ phát triển khác.
- Các thư viện nền tảng Java.
- Công cụ chẩn đoán và vận hành như `jcmd`, `jstack`, `jmap` hoặc các công cụ khác tùy bản phân phối.

JDK thông thường vẫn hỗ trợ các khả năng quen thuộc của JVM như nạp lớp, garbage collection, JIT compilation, quản lý thread và thực thi ứng dụng Java. Ứng dụng Spring Boot, ứng dụng web, ứng dụng dòng lệnh hoặc dịch vụ Java vẫn có thể chạy bình thường nếu tương thích với phiên bản JDK đó.

Tuy nhiên, một JDK không có tích hợp CRaC không thể tự tạo checkpoint của trạng thái tiến trình Java và khôi phục tiến trình từ checkpoint theo cơ chế CRaC. Việc ứng dụng có thể biên dịch và chạy trên JDK đó không chứng minh rằng JVM hỗ trợ checkpoint/restore.

Ví dụ, một nhóm có thể phát triển ứng dụng bằng JDK thông thường, tạo file JAR và chạy được ứng dụng trên máy cá nhân. Khi nhóm muốn tạo checkpoint để khởi động các instance mới nhanh hơn, họ cần kiểm tra xem bản JDK được dùng ở môi trường tạo checkpoint có hỗ trợ CRaC hay không. Nếu không có, thao tác checkpoint/restore sẽ không được JVM đó cung cấp.

## 2. Bản dựng JDK có hỗ trợ CRaC là gì?

CRaC phối hợp giữa ứng dụng Java và JVM. Ứng dụng cần có cơ hội chuẩn bị các tài nguyên trước khi trạng thái tiến trình được lưu, sau đó tái tạo hoặc kết nối lại các tài nguyên cần thiết khi tiến trình được khôi phục. JVM cần có khả năng tham gia vào vòng đời checkpoint/restore ở cấp tiến trình.

Một bản dựng JDK có hỗ trợ CRaC cung cấp phần tích hợp ở cấp runtime để thực hiện quy trình này. Tùy nhà cung cấp và phiên bản, bản dựng có thể có các thay đổi hoặc thành phần bổ sung so với bản JDK thông thường cùng dòng Java. Những phần tích hợp này cho phép môi trường chạy phối hợp với cơ chế checkpoint/restore của hệ điều hành và gọi các callback CRaC đã đăng ký.

Ở mức khái quát, quy trình gồm hai thời điểm:

1. **Trước checkpoint:** JVM yêu cầu các resource đã đăng ký chuẩn bị trạng thái. Ứng dụng có thể dừng nhận công việc mới, hoàn tất công việc đang chạy, đóng socket hoặc giải phóng tài nguyên phụ thuộc môi trường.
2. **Sau restore:** JVM tiếp tục tiến trình từ checkpoint và yêu cầu resource phục hồi. Ứng dụng có thể mở lại kết nối, tạo pool mới, làm mới thông tin xác thực hoặc khởi động lại worker nền.

Nhờ lưu lại trạng thái tiến trình sau khi ứng dụng đã khởi tạo và làm nóng, CRaC có thể giúp giảm công việc phải lặp lại khi tạo instance mới. Khả năng này phụ thuộc vào bản dựng JDK, nền tảng checkpoint/restore và cách ứng dụng quản lý tài nguyên.

## 3. So sánh hai loại JDK

| Tiêu chí | JDK thông thường | JDK có hỗ trợ CRaC |
|---|---|---|
| Chạy ứng dụng Java thông thường | Có, nếu ứng dụng tương thích | Có, nếu ứng dụng tương thích |
| JVM và các tính năng Java cơ bản | Có | Có, cùng phần tích hợp CRaC của bản dựng |
| Tạo checkpoint tiến trình theo CRaC | Không có nếu bản dựng không tích hợp CRaC | Có, trong môi trường được hỗ trợ |
| Khôi phục tiến trình từ checkpoint CRaC | Không có nếu bản dựng không tích hợp CRaC | Có, theo yêu cầu tương thích của bản dựng |
| Thực thi vòng đời callback CRaC | Không có cơ chế JVM CRaC để kích hoạt vòng đời này | JVM phối hợp callback đã đăng ký |
| API `org.crac` | Có thể dùng thư viện API làm dependency khi biên dịch, nhưng điều đó không bổ sung khả năng checkpoint vào JVM | Được dùng theo cách đóng gói và hướng dẫn của bản dựng JDK |
| Phụ thuộc môi trường hệ điều hành | Theo yêu cầu của JDK thông thường | Có thêm yêu cầu của cơ chế checkpoint/restore và bản dựng CRaC |
| Mục đích sử dụng | Phát triển, kiểm thử và chạy ứng dụng Java | Chạy ứng dụng Java và hỗ trợ quy trình checkpoint/restore |

Một bản dựng JDK có CRaC không phải là một ngôn ngữ Java khác. Mã nguồn, bytecode và phần lớn cách phát triển ứng dụng Java vẫn quen thuộc. Khác biệt quan trọng nằm ở khả năng của runtime và những yêu cầu bổ sung khi triển khai checkpoint/restore.

## 4. Phân biệt CRaC API với hỗ trợ CRaC của JVM

Đây là điểm dễ gây nhầm lẫn nhất khi thiết lập dự án.

CRaC API cung cấp các kiểu mà mã ứng dụng dùng để đăng ký và quản lý tài nguyên. API thường được sử dụng thông qua package `org.crac`, chẳng hạn:

- `Resource`: giao diện mà thành phần quản lý tài nguyên triển khai.
- `Context`: ngữ cảnh được truyền vào các callback.
- `Core`: điểm truy cập đến context CRaC toàn cục để đăng ký resource.

Trong khi đó, phần hỗ trợ CRaC ở cấp JVM chịu trách nhiệm thực hiện quy trình checkpoint và restore, đồng thời kích hoạt vòng đời resource tại đúng thời điểm.

Có thể hình dung hai phần này như sau:

```text
Mã ứng dụng Java
       |
       | triển khai và đăng ký Resource
       v
CRaC API (ví dụ: org.crac.Resource, Core, Context)
       |
       | JVM gọi callback trong vòng đời checkpoint/restore
       v
JVM từ bản dựng có hỗ trợ CRaC
       |
       | phối hợp với cơ chế checkpoint/restore của môi trường
       v
Checkpoint tiến trình  <---->  Restore tiến trình
```

**Thêm dependency API không tự biến một JDK thông thường thành JDK có CRaC.** Dependency giúp trình biên dịch nhận biết các kiểu như `Resource` và `Core`. Nó không tự bổ sung phần tích hợp cần thiết vào JVM đang chạy.

Ngược lại, chỉ cài một JDK có hỗ trợ CRaC cũng chưa bảo đảm ứng dụng đã quản lý tài nguyên đúng cách. Ứng dụng hoặc thư viện liên quan vẫn cần đăng ký và xử lý những tài nguyên có thể mất hiệu lực sau checkpoint.

### 4.1. Ví dụ khai báo API trong dự án

Một dự án có thể khai báo thư viện CRaC API làm dependency để biên dịch mã sử dụng `org.crac`. Ví dụ với Gradle:

```groovy
dependencies {
    implementation("org.crac:crac:<version-phu-hop>")
}
```

`<version-phu-hop>` là phiên bản cần chọn theo tài liệu của thư viện, framework và bản dựng JDK đang sử dụng. Không nên sao chép một phiên bản tùy ý từ dự án khác mà chưa kiểm tra tính tương thích.

Một số bản phân phối hoặc hướng dẫn tích hợp có thể cung cấp API theo cách đóng gói riêng. Hãy làm theo tài liệu của nhà cung cấp để tránh đưa vào classpath nhiều phiên bản API không tương thích.

Khi dependency đã có trong quá trình biên dịch, mã Java có thể tham chiếu đến giao diện `Resource`:

```java
import org.crac.Context;
import org.crac.Resource;

public final class CacheResource implements Resource {

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Dừng cập nhật cache và đưa tài nguyên về trạng thái an toàn.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Kiểm tra hoặc làm mới trạng thái cache sau khi restore.
    }
}
```

Thành phần quản lý resource cần được đăng ký với context phù hợp, ví dụ global context:

```java
import org.crac.Core;

CacheResource resource = new CacheResource();
Core.getGlobalContext().register(resource);
```

Đoạn mã trên thể hiện việc triển khai và đăng ký callback. Nó không tự tạo checkpoint. Việc callback có được JVM gọi hay không phụ thuộc vào runtime CRaC và quy trình checkpoint/restore thực tế.

### 4.2. Chuyện gì xảy ra nếu chỉ có API nhưng chạy bằng JDK thông thường?

Trình biên dịch có thể biên dịch mã nếu dependency cung cấp các kiểu API cần thiết. Tuy nhiên, JVM thông thường không có tích hợp CRaC sẽ không thể thực hiện checkpoint/restore chỉ nhờ dependency đó.

Hành vi cụ thể của thư viện API khi chạy trên runtime không hỗ trợ CRaC có thể phụ thuộc vào phiên bản và cách triển khai API. Một số cách tích hợp có thể cho phép ứng dụng chạy ở chế độ không checkpoint; thao tác yêu cầu checkpoint có thể thất bại hoặc báo không được hỗ trợ. Vì vậy, không nên dựa vào giả định rằng mọi API CRaC đều tự động trở thành no-op trên mọi JDK thông thường.

Nếu dự án cần chạy trên cả JDK thông thường và JDK CRaC, hãy kiểm tra tài liệu của API và framework, xác định cách phát hiện hoặc cấu hình chế độ chạy được hỗ trợ, rồi kiểm thử riêng hai runtime. Chỉ đăng ký resource chưa chứng minh rằng quy trình checkpoint/restore đã hoạt động.

## 5. Khác biệt ở vòng đời ứng dụng

Với JDK thông thường, vòng đời của một instance thường bắt đầu khi JVM khởi chạy và kết thúc khi tiến trình dừng. Ứng dụng tự khởi tạo tài nguyên, phục vụ request và đóng tài nguyên khi shutdown.

Với JDK có hỗ trợ CRaC, vòng đời có thêm điểm chuyển trạng thái: checkpoint và restore. Các tài nguyên cần được phối hợp qua hai callback chính:

| Callback | Thời điểm | Công việc thường thực hiện |
|---|---|---|
| `beforeCheckpoint(...)` | Trước khi lưu trạng thái tiến trình | Dừng nhận công việc mới, hoàn tất tác vụ đang chạy, đóng socket hoặc pool cần tạo lại |
| `afterRestore(...)` | Sau khi tiến trình được khôi phục | Mở lại kết nối, tạo pool mới, làm mới token hoặc khởi động worker |

Ví dụ, một ứng dụng kết nối đến cơ sở dữ liệu. Trên JDK thông thường, connection pool thường được tạo lúc startup và đóng lúc shutdown. Với CRaC, connection pool cần được chuẩn bị trước checkpoint và tạo lại sau restore nếu những kết nối cũ không còn hợp lệ.

Điều này đặc biệt quan trọng vì checkpoint có thể được lưu trong một khoảng thời gian trước khi sử dụng để tạo instance. Trong khoảng thời gian đó, database có thể ngắt kết nối, token có thể hết hạn, DNS có thể thay đổi hoặc môi trường mạng có thể được cấu hình lại.

## 6. Yêu cầu về hệ điều hành và môi trường chạy

Khả năng CRaC không chỉ phụ thuộc vào file JAR. Checkpoint là trạng thái của một tiến trình đang chạy, vì vậy việc tạo và khôi phục còn phụ thuộc vào cơ chế của hệ điều hành, kernel, kiến trúc CPU, container runtime và bản dựng JDK.

Trong nhiều môi trường triển khai CRaC trên Linux, CRIU (Checkpoint/Restore In Userspace) là thành phần quan trọng trong quy trình checkpoint/restore. Tùy bản phân phối JDK và cách triển khai, hệ thống có thể cần phiên bản CRIU phù hợp, kernel có tính năng cần thiết, quyền hoặc cấu hình container đặc thù và các thiết lập về filesystem.

Không nên giả định rằng một checkpoint tạo trên máy phát triển có thể được khôi phục ở bất kỳ máy chủ nào. Trước khi triển khai, cần xác nhận ma trận hỗ trợ của nhà cung cấp cho:

- Phiên bản và bản dựng JDK CRaC.
- Hệ điều hành, phiên bản kernel và kiến trúc CPU.
- Phiên bản CRIU hoặc cơ chế checkpoint/restore được bản dựng yêu cầu.
- Container runtime, quyền và cấu hình bảo mật.
- Thư viện native, đường dẫn file, mount và tài nguyên bên ngoài.
- Cách lưu trữ, phân phối và bảo vệ checkpoint.

Checkpoint cũng cần được xem là dữ liệu nhạy cảm. Bộ nhớ tiến trình có thể chứa secret, token, thông tin người dùng hoặc dữ liệu nghiệp vụ. Chỉ người và dịch vụ được phép mới nên đọc hoặc ghi checkpoint.

## 7. Cách xác định JDK đang sử dụng

Không nên chỉ nhìn vào tên thư mục cài đặt hoặc số phiên bản Java. Một máy có thể cài nhiều JDK và lệnh `java` có thể trỏ đến bản khác với `JAVA_HOME` mà công cụ build đang sử dụng.

Trước tiên, xem thông tin runtime:

```bash
java -version
```

Lệnh này giúp nhận biết phiên bản, nhà cung cấp và thông tin bản dựng mà lệnh `java` hiện tại đang gọi. Có thể xem thêm các thuộc tính môi trường:

```bash
java -XshowSettings:properties -version
```

Trong phần kết quả, chú ý các thuộc tính như `java.home`, `java.vendor`, `java.version`, `os.name` và `os.arch`. Chúng giúp xác định runtime thực tế, hệ điều hành và kiến trúc đang chạy.

Trên Windows, có thể kiểm tra đường dẫn thực thi:

```powershell
where.exe java
```

Trên Linux hoặc macOS:

```bash
which java
```

Những lệnh trên xác định runtime được shell tìm thấy. Chúng chưa đủ để kết luận runtime có hỗ trợ CRaC. Sau khi biết nhà cung cấp, phiên bản và bản dựng, hãy đối chiếu với tài liệu phát hành của đúng bản JDK đó.

## 8. Cách xác minh bản dựng có hỗ trợ CRaC

Việc xác minh nên dựa trên cả thông tin bản dựng và một phép thử checkpoint/restore trên môi trường mục tiêu.

**Bước 1: Xác định chính xác binary đang chạy.** Ghi lại kết quả `java -version`, `java.home`, `java.vendor`, `java.version` và `os.arch`. Kiểm tra cả JDK dùng để build lẫn JDK dùng khi chạy ứng dụng; hai môi trường này có thể khác nhau.

**Bước 2: Đọc tài liệu của nhà cung cấp.** Tìm đúng tên sản phẩm, phiên bản, loại build và hệ điều hành được hỗ trợ. Xác nhận bản dựng được công bố có CRaC, phiên bản API tương ứng, yêu cầu hệ thống và các tùy chọn JVM hoặc công cụ checkpoint được hỗ trợ.

**Bước 3: Kiểm tra API và dependency.** Xác nhận dự án đang dùng đúng phiên bản `org.crac` hoặc cách đóng gói API mà nhà cung cấp yêu cầu. Kiểm tra để tránh xung đột phiên bản giữa thư viện ứng dụng, framework và API được cung cấp bởi runtime.

**Bước 4: Chạy phép thử tối thiểu.** Dùng ví dụ nhỏ có một resource đã đăng ký. Khởi chạy bằng chính JDK CRaC dự kiến đưa vào triển khai, thực hiện checkpoint theo hướng dẫn của nhà cung cấp, sau đó restore từ checkpoint. Quan sát log để xác nhận callback trước checkpoint và sau restore được gọi đúng lúc.

**Bước 5: Thử trên môi trường triển khai thật.** Lặp lại phép thử trong image, kernel, container runtime, quyền và cấu hình dự kiến dùng ở production. Một phép thử thành công trên máy phát triển không bảo đảm môi trường container production cũng đáp ứng yêu cầu.

Nếu nhà cung cấp cung cấp tùy chọn JVM hoặc lệnh chẩn đoán để xác minh CRaC, hãy dùng đúng cú pháp cho phiên bản đó. Không sao chép cờ JVM từ một bản JDK khác vì tên tùy chọn, khả năng hỗ trợ và quy trình checkpoint có thể khác nhau.

## 9. Ví dụ quy trình làm việc với hai loại JDK

Một nhóm phát triển có thể dùng JDK thông thường cho một phần công việc và JDK CRaC cho kiểm thử tích hợp checkpoint/restore. Quy trình mẫu:

```text
Mã nguồn ứng dụng
       |
       v
Build và kiểm thử Java thông thường
       |
       v
Kiểm tra dependency và mã CRaC API
       |
       v
Build/khởi chạy bằng JDK có hỗ trợ CRaC
       |
       v
Khởi tạo ứng dụng và chạy warm-up
       |
       v
Tạo checkpoint theo tài liệu của bản JDK
       |
       v
Restore trong môi trường tương thích
       |
       v
Kiểm tra callback, kết nối, readiness và request
```

Trong CI/CD, có thể tổ chức các job riêng:

| Job | Runtime | Mục đích |
|---|---|---|
| Compile và unit test | JDK tiêu chuẩn của dự án | Kiểm tra mã nguồn, logic nghiệp vụ và tương thích Java cơ bản |
| CRaC integration test | Bản dựng JDK có hỗ trợ CRaC | Kiểm tra resource callback và khả năng checkpoint/restore |
| Restore test | Cùng bản dựng và môi trường tương thích | Xác minh checkpoint có thể khôi phục và ứng dụng sẵn sàng |
| Deployment validation | Runtime thực tế của production | Xác minh image, kernel, quyền và tài nguyên bên ngoài |

Không phải dự án nào cũng cần chạy trên hai loại JDK. Nếu production chỉ dùng JDK CRaC, có thể chọn chính bản dựng đó làm runtime chính cho build và integration test để giảm khác biệt môi trường. Nếu ứng dụng cần tương thích nhiều runtime, cần duy trì kiểm thử tương ứng.

## 10. Những nhầm lẫn thường gặp

### 10.1. Nghĩ rằng mọi JDK cùng phiên bản Java đều có CRaC

Phiên bản Java cho biết dòng nền tảng và tính năng Java tương ứng. Nó không tự chứng minh rằng nhà cung cấp đã tích hợp CRaC vào bản dựng. Cần kiểm tra đúng artifact và tài liệu phát hành.

### 10.2. Nghĩ rằng thêm dependency CRaC là đủ

Dependency cung cấp API để mã nguồn tham chiếu đến `Resource`, `Context` hoặc `Core`. Khả năng tạo và khôi phục checkpoint cần được hỗ trợ ở runtime. Một JDK thông thường không được bổ sung tính năng checkpoint/restore chỉ bằng cách thêm dependency.

### 10.3. Nghĩ rằng JDK CRaC chỉ chạy được ứng dụng đặc biệt

JDK có hỗ trợ CRaC vẫn là môi trường chạy Java. Ứng dụng Java thông thường vẫn có thể chạy nếu tương thích với bản JDK. CRaC bổ sung một khả năng vận hành; ứng dụng chỉ hưởng lợi khi được chuẩn bị cho vòng đời checkpoint/restore.

### 10.4. Nghĩ rằng có thể tạo checkpoint trên một JDK rồi restore bằng JDK bất kỳ

Checkpoint chứa trạng thái của một tiến trình cụ thể, bao gồm trạng thái runtime và tài nguyên hệ thống. Nó không giống file JAR hay bộ bytecode độc lập. Việc restore cần bản dựng và môi trường đáp ứng yêu cầu tương thích của nhà cung cấp.

### 10.5. Nghĩ rằng đăng ký `Resource` đồng nghĩa với đã hỗ trợ CRaC

Đăng ký resource chỉ khai báo cách ứng dụng chuẩn bị và phục hồi tài nguyên. Cần thực hiện checkpoint và restore thật trên JDK có hỗ trợ, rồi kiểm tra callback được gọi và tài nguyên hoạt động chính xác.

### 10.6. Nghĩ rằng JDK CRaC luôn làm ứng dụng chạy nhanh hơn

CRaC giúp tái sử dụng trạng thái đã chuẩn bị khi restore. Nó không bảo đảm mọi request nhanh hơn trong mọi tình huống. Nếu checkpoint được tạo trước warm-up, hoặc restore mất nhiều thời gian để tạo lại kết nối và tải dữ liệu, lợi ích tổng thể có thể thấp hơn mong đợi. Cần benchmark cùng điều kiện với startup thông thường.

## 11. Tiêu chí lựa chọn JDK cho dự án

Khi chọn JDK, hãy bắt đầu từ yêu cầu triển khai của ứng dụng.

Nếu ứng dụng chỉ cần chạy Java theo cách thông thường, JDK được hỗ trợ và tương thích với framework có thể đáp ứng đầy đủ. Không cần chọn một bản dựng CRaC chỉ vì nó có thêm tính năng.

Nếu mục tiêu là giảm thời gian tạo instance mới bằng checkpoint/restore, hãy chọn một bản dựng JDK có CRaC được nhà cung cấp hỗ trợ cho môi trường triển khai. Sau đó xác minh API, hệ điều hành, kernel, container runtime và các thư viện liên quan.

Nếu ứng dụng cần chạy ở nhiều môi trường, ví dụ máy phát triển dùng JDK thông thường nhưng production dùng JDK CRaC, hãy xác định rõ cách quản lý dependency và chế độ chạy. CI cần có ít nhất một bài kiểm thử tích hợp chạy bằng runtime CRaC thực tế; unit test trên JDK thông thường không thay thế được bài kiểm thử này.

Một số tiêu chí nên được ghi lại trong tài liệu dự án:

- Nhà cung cấp và tên bản phân phối JDK.
- Phiên bản Java, số build và bản vá cụ thể.
- Nơi lấy binary và cách cố định phiên bản trong build/deploy.
- Phiên bản CRaC API và các framework có tích hợp CRaC.
- Hệ điều hành, kernel, kiến trúc CPU và container runtime được hỗ trợ.
- Công cụ hoặc dịch vụ checkpoint/restore cần có.
- Quy trình tạo, lưu, phân phối, khôi phục và xóa checkpoint.
- Kết quả kiểm thử callback, readiness, latency và tỷ lệ lỗi sau restore.

## 12. Checklist xác minh trước khi sử dụng CRaC

- [ ] Đã xác định đúng JDK binary đang dùng để build và chạy ứng dụng chưa?
- [ ] Đã ghi nhận nhà cung cấp, phiên bản, số build và kiến trúc chưa?
- [ ] Tài liệu nhà cung cấp xác nhận đúng bản dựng đó hỗ trợ CRaC chưa?
- [ ] Phiên bản `org.crac` hoặc cách đóng gói API có tương thích không?
- [ ] Đã xác nhận hệ điều hành, kernel, CRIU hoặc cơ chế checkpoint/restore được yêu cầu chưa?
- [ ] Container runtime và quyền cần thiết đã được cấu hình chưa?
- [ ] Resource đã đăng ký và có logic phù hợp cho cả hai callback chưa?
- [ ] Phép thử đã tạo checkpoint và restore thành công trên runtime mục tiêu chưa?
- [ ] Đã xác nhận kết nối, worker nền, secret và readiness sau restore chưa?
- [ ] Checkpoint được lưu trữ và phân quyền như dữ liệu nhạy cảm chưa?
- [ ] CI/CD có kiểm thử bằng đúng bản dựng JDK CRaC dự kiến triển khai không?

## Kết luận

JDK thông thường và bản dựng JDK có hỗ trợ CRaC đều có thể chạy ứng dụng Java. Khác biệt cốt lõi là khả năng của JVM: JDK thông thường không có tích hợp CRaC nếu bản dựng không cung cấp tính năng này, trong khi JDK CRaC có thể phối hợp checkpoint và restore tiến trình trong môi trường được hỗ trợ.

CRaC API và CRaC runtime là hai phần liên quan nhưng không thay thế cho nhau. API giúp ứng dụng đăng ký resource và định nghĩa cách chuẩn bị hoặc phục hồi tài nguyên. Bản dựng JDK có hỗ trợ CRaC cung cấp tích hợp ở cấp JVM để thực hiện vòng đời checkpoint/restore. Vì vậy, hãy xác minh đúng bản dựng JDK, dependency API và môi trường hệ điều hành, rồi chạy một phép thử restore thực tế trước khi đưa CRaC vào triển khai.
