# 3.8 Phân biệt thông tin có sẵn với thông tin nhạy cảm cần loại bỏ trước khi chia sẻ

Khi điều tra sự cố Java, người vận hành thường thu thập PID, lệnh khởi động, phiên bản JVM, system properties, biến môi trường, thread dump, GC log, JFR hoặc heap dump. Một phần những thông tin này đã có sẵn trong tiến trình, hệ điều hành hay nền tảng quan sát; tuy nhiên **có thể truy cập được không đồng nghĩa được phép chia sẻ nguyên văn**.

Ví dụ, `jcmd PID VM.command_line` có thể giúp đối chiếu JVM flags, nhưng các tham số khởi động có thể chứa mật khẩu hoặc API key nếu ứng dụng từng nhận bí mật qua `-D...`. `ProcessHandle.Info.commandLine()` có thể cung cấp command line theo khả năng OS; nó không phải cơ chế tự động lọc dữ liệu riêng tư. Một heap dump có thể chứa object, token và thông tin cá nhân đang nằm trong bộ nhớ. Đăng nguyên đầu ra lên issue công khai có thể biến hoạt động chẩn đoán thành sự cố lộ dữ liệu.

Bài này tập trung vào ranh giới giữa **thông tin sẵn có để quan sát** và **thông tin an toàn, cần thiết để chia sẻ** trong ngữ cảnh *tiến trình và môi trường* của Java. Mục tiêu là biết thu đúng bằng chứng, phân loại rủi ro, loại bỏ hoặc biến đổi thông tin nhạy cảm có kiểm chứng, rồi chia sẻ đúng phạm vi người nhận mà vẫn giữ giá trị điều tra.

## 1. Hai câu hỏi độc lập: “có lấy được không?” và “có nên đưa cho ai?”

### 1.1 “Có sẵn” chỉ nói về khả năng quan sát

Một trường dữ liệu có thể lấy từ nhiều nguồn:

- JVM/Java API: `System.getProperty`, `ManagementFactory`, `ProcessHandle` hoặc MBeans.
- JDK tools: `jps`, `jcmd`, JFR, GC logs và các diagnostic commands được JVM đích hỗ trợ.
- Hệ điều hành: process list, command line, environment, file descriptors, user, memory mapping, file paths hoặc crash artifacts.
- Nền tảng triển khai: container/pod metadata, runtime parameters, service labels, image names, logs và metrics.
- Ứng dụng: request/trace ID, exception stack trace, URL, HTTP headers, SQL/DB connection details, payload và thông tin phiên người dùng.

Khả năng quan sát luôn có giới hạn về **quyền**, thời điểm, namespace, phiên bản công cụ và cấu hình runtime. Ví dụ, Java `ProcessHandle.Info.arguments()` trả `Optional` và có thể không cung cấp giá trị; `jcmd` có thể không attach được vào JVM đích. **Không đọc được** không có nghĩa dữ liệu không tồn tại; **đọc được** cũng không có nghĩa dữ liệu đã được làm sạch.

### 1.2 “Có thể chia sẻ” phụ thuộc ngữ cảnh và người nhận

Cùng một thông tin có thể phù hợp trong một incident room nội bộ nhưng không phù hợp trong forum công khai, issue gửi vendor hoặc screenshot trên mạng xã hội. Cần biết:

1. **Mục đích**: người nhận cần xác minh Java version, heap size, stack trace hay chính xác endpoint nào?
2. **Đối tượng nhận**: nhóm vận hành có quyền, người hỗ trợ từ đối tác, cộng đồng công khai hay hệ thống ticket/AI bên thứ ba?
3. **Mức nhạy cảm**: secret, dữ liệu cá nhân, định danh khách hàng, hạ tầng nội bộ, chi tiết cấu hình/phòng thủ hoặc thông tin kinh doanh?
4. **Quy tắc áp dụng**: chính sách tổ chức, phạm vi được phép cung cấp dữ liệu, thời hạn lưu và quyền truy cập.
5. **Giá trị chẩn đoán**: trường nào thực sự cần để kiểm chứng giả thuyết, trường nào chỉ “có vì tool in ra”?

Một PID hoặc phiên bản Java thường có rủi ro thấp hơn access token, nhưng vẫn cần xét bối cảnh: phiên bản lộ ra cùng hostname nội bộ, IP, build ID, đường dẫn riêng tư hay kiến trúc deployment có thể tạo ra thông tin nhạy cảm khi ghép lại.

**Nguyên tắc cốt lõi:** chọn *mức thông tin tối thiểu đủ giải thích hiện tượng* và chỉ chia sẻ với người được phép. Không có một danh sách trường “an toàn công khai trong mọi tình huống”.

## 2. Nhóm thông tin theo rủi ro, không chỉ theo tên công cụ

Một cách phân loại phục vụ thực hành:

| Nhóm | Ví dụ trong Java diagnostics | Cách xử lý mặc định trước khi chia sẻ rộng |
| --- | --- | --- |
| **Thông tin kỹ thuật ít nhạy cảm** | Java major version, loại GC, heap max, số thread, tổng CPU time | Kiểm tra ngữ cảnh và người nhận; có thể chia sẻ số liệu tổng hợp nếu cần |
| **Thông tin môi trường/nội bộ** | Hostname, container ID, namespace, path, private IP, image registry, tên service, cấu trúc package nội bộ | Dùng alias hoặc mô tả chức năng, bỏ phần định danh không cần |
| **Thông tin tài khoản/cá nhân** | User name, email, customer ID, session ID, request payload, ID trong URL | Xóa, tổng hợp hoặc dùng mã thay thế có kiểm soát |
| **Bí mật truy cập** | Password, bearer token, API key, private key, cookie phiên, credential URL, cloud secret | Không đưa vào bản chia sẻ; nếu đã lộ, xử lý như sự cố credential |
| **Dữ liệu chẩn đoán thô có rủi ro cao** | Heap dump, core dump, request/body logs, `/proc/PID/environ`, full JFR hoặc `hs_err_pid` | Lưu trong kênh được bảo vệ; chỉ cung cấp trích xuất đã rà soát hoặc qua quy trình được duyệt |

Phân loại này nhằm ra quyết định, không phải cam kết rằng mọi số “ít nhạy cảm” đều tự động công khai được. **Độ nhạy có thể đến từ sự kết hợp**: riêng p95 của API ít tiết lộ, nhưng khi gắn với customer ID, payload, địa chỉ nội bộ và thời điểm chính xác thì có thể xác định được giao dịch riêng lẻ.

Cũng phân biệt:

- **Dữ liệu bí mật (secret)**: ai biết giá trị có thể được cấp quyền hoặc giả mạo (token, khóa, mật khẩu). Với secret, che một vài ký tự cuối thường **không đủ**.
- **Dữ liệu cá nhân**: liên quan tới người cụ thể, có thể xuất hiện trong tên thread, log, URL, SQL, stack trace hoặc snapshot heap.
- **Thông tin nội bộ/nhạy cảm hệ thống**: không nhất thiết là password nhưng tiết lộ topology, tên máy, mạng riêng, repository, cơ chế phòng vệ hoặc cấu hình vận hành.
- **Thông tin tương quan**: trace ID, span ID, correlation ID, timestamp; đôi khi cần giữ để truy vết, nhưng có thể nối với dữ liệu khác. Chỉ giữ khi mục đích và đối tượng cho phép.

## 3. Những nguồn tưởng chỉ là “thông tin hệ thống” nhưng có thể chứa dữ liệu nhạy cảm

### 3.1 Command line và JVM arguments

Các nguồn phổ biến:

```bash
jps -v
jcmd 4242 VM.command_line
ps -p 4242 -o pid,args
```

Các lệnh trên minh họa cách truy vấn PID `4242` trên một môi trường phù hợp; PID không phải kết quả thực tế và lệnh `ps` dùng cú pháp Linux/Unix. `jcmd` cần quyền/attach và hỗ trợ từ JVM đích; `jps` chỉ nhìn thấy các JVM mà công cụ nhận diện được.

Một command line có thể chứa:

- `-Xmx`, `-Xms`, `-XX:+...`: thường hữu ích để điều tra heap/GC, nhưng cũng cần xét thông tin cấu hình nội bộ.
- `-Dservice.env=...` hoặc `-Dconfig.path=...`: tiết lộ tên môi trường và đường dẫn nội bộ.
- `-Dapi.token=...`, `--password=...` hoặc URL chứa `user:password@host`: **bí mật cần loại bỏ**, cho dù chúng được truyền vào JVM dưới dạng tham số.
- Main class, JAR path, account name, installation directory: có thể lộ cấu trúc hệ thống hoặc user account.

Đầu ra của `jps -v` và `jcmd VM.command_line` có thể khác nhau về loại thông tin và độ đầy đủ; **không được dùng một đầu ra thiếu secret làm bằng chứng các nguồn khác cũng sạch**.

**Ví dụ dữ liệu giả định, không chứa credential thật:**

```text
java -Xmx512m -Dservice.env=staging -Dapi.token=DEMO_ONLY_NOT_VALID -jar order-api.jar
```

Trước khi gửi ra phạm vi rộng hơn, không nên đăng nguyên văn ví dụ kiểu này khi giá trị là thật. Một bản chia sẻ minh họa có thể là:

```text
Java launcher: java -jar <application.jar>
Heap max setting: -Xmx512m
Sensitive JVM properties: [REDACTED]
Runtime profile: staging (chỉ giữ nếu được phép)
```

Giữ `-Xmx512m` vì liên quan điều tra heap; loại **cả giá trị và chi tiết thừa** của property nhạy cảm. Nếu tên service hoặc tên môi trường cũng nhạy cảm, dùng tên trung tính hoặc loại trường.

### 3.2 System properties không đồng nhất với biến môi trường

`System.getProperties()` và một số lệnh VM có thể trả Java **system properties**. `System.getenv()` trả **environment variables** mà tiến trình nhìn thấy, trong phạm vi OS/runtime cho phép. Hai nguồn khác nhau và không bảo đảm mọi giá trị thuộc nguồn này đều có mặt ở nguồn kia.

Ví dụ, property `user.home`, `user.name`, `java.class.path` có thể chứa tên người dùng, path dự án, package/class names và thư mục triển khai. Property do ứng dụng tự tạo có thể chứa secret nếu cấu hình sai. Environment variables lại thường được dùng để đưa cấu hình/credential vào container; chúng không an toàn chỉ vì “không xuất hiện trong args”.

Trên Linux, khi có đủ quyền, `/proc/<PID>/environ` có thể chứa dữ liệu môi trường tại phạm vi kernel cung cấp; nội dung có thể không phản ánh mọi thay đổi về sau, tùy cơ chế thực thi. **Không đưa file đó nguyên văn vào ticket.** Các dòng `docker inspect`, pod configuration hay snapshot diagnostics cũng có thể chứa env values hoặc references tới secret; không suy ra rằng công cụ “chỉ đọc metadata” là đã loại thông tin nhạy cảm.

Khi cần đối chiếu runtime, nên hỏi đúng trường: **tên biến nào đang được khai báo**, giá trị có mặt hay không, profile/phiên bản cấu hình nào đang sử dụng. Với credential, mô tả “credential configured/present” thường đủ hơn việc in giá trị.

### 3.3 ProcessHandle và process listing

Java `ProcessHandle.Info` có thể cung cấp:

- `command()`: đường dẫn/name executable (tùy hệ điều hành và quyền).
- `commandLine()` và `arguments()`: command line/argv dạng best-effort, có thể thiếu và có thể mang secret.
- `user()`: account chạy process, có thể là thông tin nội bộ/cá nhân.
- `startInstant()` và `totalCpuDuration()`: thời điểm khởi động, CPU time tích lũy, nếu được hỗ trợ.

Những phương thức này trả `Optional`; không được tự điền chuỗi rỗng thành “an toàn” hoặc suy từ tên executable rằng argument không có bí mật. Nếu chỉ cần PID và JVM version, **không cần thu `commandLine()` hoặc `user()`**.

`ProcessHandle.allProcesses()` liệt kê nhiều loại native process nhìn thấy được, không chỉ Java. Đem nguyên danh sách vào báo cáo có thể lộ phần mềm, tài khoản, dịch vụ nền và quy ước đặt tên trên máy không liên quan đến sự cố.

### 3.4 Thread dumps, stack traces và exception messages

Thread dump cung cấp stack, thread name và trạng thái, giúp chẩn đoán blocked/deadlock hoặc thread pool. Dù một stack trace thường chứa tên class/method hơn là request payload, dữ liệu nhạy cảm vẫn có thể nằm ở:

- Tên thread được ứng dụng đặt từ user/customer/request ID.
- Exception message chứa URL, query parameter, SQL literal, tên file hoặc dữ liệu đầu vào.
- Thông tin lock/monitor, package nội bộ, tên thư viện/phiên bản thể hiện kiến trúc.
- Log hoặc báo cáo kết hợp thread dump với metadata request.

Không kết luận “thread dump chắc chắn không chứa secret”; cũng không tự động xóa mọi class name nếu nhóm kỹ thuật cần stack để xác định mã gây treo. **Giữ những frame liên quan và thay tên định danh nhạy cảm bằng nhãn nhất quán** khi được phép.

### 3.5 GC logs, metrics và JFR

GC log thường có thời gian, heap regions, pause và flags, giúp phân biệt GC pressure. Tuy nhiên path, JVM arguments, PID, hostname, target filename hoặc dòng startup được cấu hình in kèm có thể tiết lộ thông tin nội bộ.

Metrics có thể chứa label như `customer_id`, `user_id`, `tenant`, private endpoint hoặc path. Một số nhãn có **cardinality cao** và đồng thời là nguy cơ riêng tư. Khi chia sẻ, hãy giữ giá trị tổng hợp mà vẫn đủ so sánh và loại nhãn định danh không cần.

JFR recording có thể gồm stack trace, thread names, exception events, class/method names, allocation events, file/socket context và các event khác tùy cấu hình/phiên bản. Nó **không phải file “đã ẩn danh” theo mặc định**; công cụ phân tích có thể cho thấy chi tiết không hiển thị trên một screenshot. Trước khi gửi JFR ra ngoài, cần xét event nào được ghi, dữ liệu nào nhạy cảm, liệu trích thống kê hoặc export đã lọc đủ thay cho toàn bộ recording.

### 3.6 Heap dump và core dump: rủi ro cao hơn bản text thông thường

Heap dump là ảnh chụp dữ liệu object trong JVM, có thể chứa `String`, cache, thông tin request/session, token, cấu hình, dữ liệu nghiệp vụ và các reference graph. Core dump/native crash dump có thể chứa vùng nhớ tiến trình, không chỉ stack trace. File `hs_err_pid*.log` hoặc báo cáo crash có thể lộ thông số, đường dẫn, environment và mapping khác nhau theo phiên bản.

**Không thử “tìm rồi thay chuỗi” bằng text editor trên file heap dump nhị phân** rồi coi đó là đã redacted. Cấu trúc dump và nội dung nhị phân đòi hỏi công cụ hiểu định dạng; loại bỏ một chuỗi nhìn thấy không bảo đảm dữ liệu biến mất khỏi bản dump. Với trường hợp cần chia sẻ:

1. Giữ file gốc ở kênh hạn chế quyền và bảo vệ theo chính sách.
2. Ưu tiên xuất **báo cáo dẫn xuất**: histogram loại object, tổng retained bytes, stack/frame hoặc thống kê allocation đủ cho câu hỏi.
3. Nếu bắt buộc gửi dump gốc cho bên có quyền, dùng quy trình chuyển giao, mã hóa, thời hạn lưu và phê duyệt dữ liệu tương ứng; kiểm tra phạm vi người nhận và khả năng thu hồi.
4. Không gửi heap dump qua kênh chat, issue hoặc kho lưu công khai chỉ vì công cụ tạo file dễ dàng.

## 4. Ma trận quyết định: giữ, thay thế, tổng hợp hay loại bỏ?

Khi xử lý một trường, chọn thao tác dựa trên cả độ nhạy và giá trị chẩn đoán:

| Trường ví dụ | Có ích cho điều tra gì? | Xử lý trước khi chia sẻ ngoài nhóm sở hữu |
| --- | --- | --- |
| `java.version` hoặc JVM implementation | Khác biệt runtime/JIT/GC, tương thích | Giữ khi cần và được phép; đôi khi chỉ cần Java major version |
| `-Xmx512m`, GC type, thread count | Heap sizing, GC/threads | Có thể giữ nếu không tiết lộ cấu hình bị hạn chế |
| PID và start time | Xác nhận đúng instance | Giữ nội bộ; có thể đổi thành `process-A` ở bản công khai |
| Full hostname, private IP, pod UID | Correlation với hạ tầng | Thay bằng `host-A`, `container-1` hoặc tổng hợp |
| Executable path có tên user | Xác định runtime binary | Giữ loại executable, ẩn phần thư mục định danh |
| System property `api.key` | Kiểm tra credential có cấu hình | Chỉ báo trạng thái “configured”; xóa tên/giá trị nếu không cần |
| Cookie, Authorization header, URL có token | Điều tra xác thực/giao dịch | Không đưa giá trị; mô tả loại header, tình trạng xuất hiện hoặc status code |
| Email, user/customer ID | Correlation sự kiện | Thay bằng ID ngẫu nhiên hoặc pseudonym có quản lý, bỏ nếu không cần |
| Request body / SQL với giá trị thật | Tái hiện logic nghiệp vụ | Dùng synthetic payload, parameter placeholders hoặc kiểu dữ liệu |
| Stack trace | Chẩn đoán exception, lock, deadlock | Giữ frame liên quan, bỏ message/IDs/paths nhạy cảm |
| Heap/core dump, full JFR | Điều tra memory/native crash, event detail | Chia sẻ bản dẫn xuất đã duyệt; raw file phải ở kênh có kiểm soát |

**Bốn hình thức xử lý chính:**

- **Giữ nguyên có điều kiện:** trường ít nhạy cảm, thật sự cần, người nhận phù hợp.
- **Thay thế (redact/mask):** bỏ giá trị nhạy cảm, dùng `[REDACTED]` hoặc alias giữ quan hệ kỹ thuật.
- **Tổng hợp:** chỉ chia sẻ count, rate, percentile, range, nhóm lỗi hoặc kết quả bucket thay cho từng người/yêu cầu.
- **Loại bỏ:** trường không liên quan hoặc quá nhạy cảm để chia sẻ trong mục đích này.

Đôi khi **chỉ giữ dấu “có hay không”** cũng tiết lộ điều không được phép công bố, chẳng hạn sự tồn tại của hệ thống nội bộ hoặc một cơ chế khóa cụ thể. Khi đó bỏ cả tên trường khỏi phiên bản chia sẻ.

## 5. Quy trình làm sạch bằng chứng trước khi chia sẻ

### 5.1 Bước 1: xác định mục đích và phạm vi người nhận

Viết một câu hỏi đủ hẹp: “Nhờ xác minh pause GC tăng khi JVM dùng G1 với heap 512 MiB” hoặc “Cần phân tích stack của thread BLOCKED”. Đừng đặt mục tiêu rộng kiểu “gửi hết mọi diagnostics để người khác tự xem”.

Gắn nhãn đối tượng nhận:

- **Nội bộ nhóm chịu trách nhiệm:** có thể được xem nhiều bằng chứng hơn, vẫn cần least privilege.
- **Các nhóm nội bộ khác / vendor support:** chỉ có dữ liệu được phép chia sẻ theo hợp đồng/quy trình; cắt những trường không cần.
- **Issue công khai, forum, tài liệu học, dịch vụ bên ngoài:** mặc định dùng synthetic examples hoặc báo cáo tối thiểu đã rà soát.

Một dịch vụ AI ngoài hệ thống cũng là **người nhận dữ liệu qua một kênh chia sẻ**. Không paste credential, heap dump hay raw logs lên bất kỳ công cụ nào chỉ vì muốn nhanh chóng tìm nguyên nhân; trước hết phải xác định chính sách và mục đích truyền dữ liệu.

### 5.2 Bước 2: thu dữ liệu tối thiểu ngay từ nguồn

Nếu chỉ cần Java version và heap limit, hãy lấy những trường đó; không thu toàn bộ system properties hoặc environment rồi hy vọng regex lọc hết. Một số nguyên tắc:

1. Ưu tiên metrics đã được tổng hợp, API trả field cụ thể hoặc lệnh read-only đúng mục tiêu.
2. Tránh bật debug logging có thể ghi request body/header thật nếu chưa cần.
3. Tránh bật thêm profiler/dump nặng chỉ để hỗ trợ một câu hỏi nhỏ.
4. Không đưa output raw lên terminal được ghi tự động bởi log chia sẻ rộng quyền nếu nó có thể chứa secret.
5. Nếu cần giữ raw evidence để forensic nội bộ, lưu riêng trong vùng hạn chế quyền, mã hóa và chính sách retention phù hợp; bản chia sẻ là bản sao đã làm sạch.

Cách tiếp cận tốt nhất là **không thu/không xuất dữ liệu nhạy cảm khi câu hỏi không cần nó**. Redaction sau khi thu vẫn là lớp phòng vệ cần thiết nhưng không thay được nguyên tắc tối thiểu hóa.

### 5.3 Bước 3: phân loại trường và các vị trí dữ liệu có thể ẩn

Với mỗi artifact, rà soát:

- **Key/value đơn giản:** `password`, `passwd`, `secret`, `token`, `apiKey`, `Authorization`, `Cookie`, `privateKey` và tên biến theo ứng dụng.
- **Giá trị nằm trong chuỗi khác:** query parameter, URL userinfo, connection string, JDBC URL, header line, JSON lồng nhau, YAML, JVM `-D...`, command-line arguments.
- **Dữ liệu được mã hóa/đóng gói:** URL encoding, Base64, escaped JSON, multiline PEM hoặc log chunk; việc không thấy từ “password” không chứng minh sạch.
- **Danh tính gián tiếp:** email, phone, tên người dùng trong path, IP, customer ID, session ID, device ID, trace ID, tenant/domain.
- **Metadata của artifact:** tên file, title, folder path, link chia sẻ, comment, revision history, attachment description, timestamp và thông tin người tạo.

Dùng công cụ phát hiện tự động như **một bước hỗ trợ**, không coi kết quả “0 match” là chứng nhận an toàn. Secret có thể mang tên tùy biến; dữ liệu dạng free text, binary, hoặc cấu trúc bất ngờ có thể thoát khỏi regex.

### 5.4 Bước 4: làm sạch bằng cách phù hợp loại dữ liệu

**Dữ liệu có cấu trúc:** chọn allowlist field trước khi xuất. Ví dụ, xuất `java.version`, `heap.max.bytes` và GC type thay vì serialize `System.getProperties()`. Với JSON/YAML hãy parse theo cấu trúc, lọc field, sau đó serialize lại; tránh replace text tùy tiện dễ bỏ sót nested fields hoặc tạo output sai.

**Command line:** không bảo đảm parse được chỉ bằng `split(" ")` vì quoting/escaping khác giữa shell và OS. Nếu cần share JVM flags, lấy riêng flags không nhạy cảm có mục đích; đừng tạo “sanitizer command line” kiểu thay dấu bằng regex rồi tin tuyệt đối. Khi một `-D...` chứa secret, có thể mô tả “sensitive property configured” thay vì ghi tên và giá trị.

**URL/connection string:** một URL có thể mang username/password trong authority, query, path hoặc fragment. JDBC connection strings có nhiều cú pháp theo driver. Tốt hơn dùng chuỗi đại diện hoặc phân tích cú pháp theo driver/protocol rồi chỉ giữ scheme, loại kết nối và đặc trưng cần điều tra; **không** tự động coi URI không có `@` là an toàn.

**Text log/stack trace:** giữ những frame, mã lỗi và chuỗi thời gian cần thiết; cắt message chứa dữ liệu khách hàng; thay tên người/host bằng alias nhất quán nếu correlation có ích. Kiểm tra phần trước/sau đoạn thay thế để không còn bản sao ở field khác hoặc nested exception.

**Dump/binary:** không redaction bằng phép replace bytes mù quáng. Trích báo cáo từ công cụ phân tích, rồi rà soát báo cáo dẫn xuất. Raw dump ở kho có quyền hạn chế.

**Hình ảnh/screenshot:** cắt/che giá trị trong ảnh, nhưng cũng kiểm tra thông tin ở tab khác, tooltip, title, URL trình duyệt, metadata và tên file. Nếu có thể, tạo ảnh từ output đã làm sạch thay vì chụp raw rồi dùng một hình chữ nhật đè lên secret.

### 5.5 Bước 5: kiểm tra bản sẽ chia sẻ, không kiểm tra nhầm bản gốc

Cần kiểm tra **artifact cuối cùng** theo đúng định dạng mà người nhận sẽ mở:

1. Đọc toàn bộ bản xuất, kể cả file đính kèm, phần collapsed, metadata hoặc các dòng cuối bị cắt.
2. Tìm pattern credential, URL, IP, email, username, token-like strings, secret-specific key names và giá trị nhạy cảm đã biết.
3. Kiểm tra alias được thay **nhất quán** để vẫn lần theo được một process/request khi cần, nhưng không mang định danh thật.
4. Thử xem người nhận có thể khôi phục dữ liệu từ base64, HTML source, comment/revision, file gốc được nhúng hoặc link tới raw evidence hay không.
5. Xác nhận người nhận, quyền link, thời hạn tồn tại và kênh chuyển giao; chỉ chia sẻ sau khi nội dung phù hợp phạm vi đã định.

**Redaction trực quan chưa chắc là redaction thực tế.** Ví dụ một ô bảng tính hiển thị `[REDACTED]` nhưng vẫn có note/comment hoặc phiên bản cũ; một PDF có hình chữ nhật đen đè lên chữ chưa chắc loại được text layer; một file log nén còn chứa raw secret. Phải kiểm tra lớp dữ liệu thực và bản chia sẻ cuối.

### 5.6 Bước 6: giữ dấu vết và xử lý sự cố lộ secret

Nên lưu trong hồ sơ điều tra nội bộ:

- Nguồn dữ liệu, thời gian, PID/host/container scope và command/collector đã dùng.
- Các loại field được giữ/loại/tổng hợp, phương pháp, phiên bản script/policy.
- Người rà soát và đối tượng nhận; hash/checksum artifact dẫn xuất nếu cần tính toàn vẹn.
- Vị trí raw evidence được bảo vệ và thời gian xóa theo quy trình; tránh ghi trực tiếp secret vào hồ sơ phê duyệt.

Nếu một credential thật đã được đưa ra kênh ngoài phạm vi, **xóa message chưa chắc đủ** vì có log, bản sao, cache hoặc lịch sử. Cần xử lý theo quy trình incident của tổ chức: thông báo bên phụ trách, thu hồi/rotate secret khi thích hợp, đánh giá phạm vi lộ và kiểm soát bản sao. Không tự công bố giá trị để “chứng minh đã lộ”.

## 6. Ví dụ đối chiếu trước–sau: giữ giá trị chẩn đoán

Giả sử một JVM bị tăng heap occupancy trong môi trường thử nghiệm. Bản **giả lập** có dữ liệu sau (mọi tên, domain và token đều chỉ là ví dụ không có giá trị sử dụng):

```text
Captured at: 2026-10-29T08:00:00Z
Process PID: 4242
Java version: 21.0.4
JVM: -Xms256m -Xmx512m -Dapi.token=DEMO_ONLY_INVALID
Run as: demo-user
Home: /home/demo-user/apps/order
DB: jdbc:postgresql://db.internal.invalid:5432/orders?password=DEMO_ONLY_INVALID
Authorization: Bearer DEMO_ONLY_INVALID
Heap used: 420 MiB
Heap max: 512 MiB
```

Nếu chia sẻ nội bộ cho đồng nghiệp chỉ cần phân tích heap, một phiên bản phù hợp **sau khi được kiểm tra theo quyền người nhận** có thể là:

```text
Capture time (UTC): 2026-10-29T08:00:00Z
Process: instance-A
Runtime: Java 21
Heap flags: -Xms256m -Xmx512m
Heap used: 420 MiB
Heap max: 512 MiB
Startup properties outside approved fields: omitted
Account, paths, DB endpoint, credentials, authorization header: omitted
```

Bản thứ hai vẫn giúp đánh giá heap occupancy và sizing. Nó **không** còn chứa thông tin đủ để kết nối database, giả mạo phiên, tìm tên tài khoản hay suy ra đường dẫn thực. Khi cần so hai lần chẩn đoán cùng instance, giữ alias `instance-A` trong một hồ sơ nội bộ có mapping bảo vệ; không cần đăng mapping ra ngoài.

Nếu mục tiêu là kiểm tra chính DB latency, có thể giữ “database dependency = PostgreSQL” hoặc thống kê p95 truy vấn sau khi loại host/account/credential. Không nên làm mất toàn bộ bằng chứng kỹ thuật nếu có thể giữ bản tổng hợp an toàn hơn.

## 7. Thực hành Java 17+: báo cáo allowlist thay vì in nguyên dữ liệu

Ví dụ dưới đây tạo **dữ liệu giả định trong bộ nhớ** và chỉ xuất những trường được cho phép. Không truy cập process của người khác, không thu environment thật và không tạo secret có hiệu lực. Vì vậy stdout có thể kiểm tra chính xác trên Java 17+.

Lưu tệp `DiagnosticDisclosureDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DiagnosticDisclosureDemo {
    public static void main(String[] args) {
        // Mọi giá trị đều là dữ liệu mô phỏng, không phải secret thật.
        Map<String, String> observed = new LinkedHashMap<>();
        observed.put("timestamp.utc", "2026-10-29T08:00:00Z");
        observed.put("jvm.version", "21.0.4");
        observed.put("pid", "4242");
        observed.put("heap.max.bytes", "536870912");
        observed.put("os.user", "demo-user");
        observed.put("db.url", "jdbc:postgresql://db.internal.invalid/orders");
        observed.put("api.token", "DEMO_ONLY_INVALID");
        observed.put("process.commandLine", "java -Dapi.token=DEMO_ONLY_INVALID");

        List<String> allowedFields = List.of(
                "timestamp.utc",
                "jvm.version",
                "pid",
                "heap.max.bytes"
        );

        int omitted = observed.size();
        for (String key : allowedFields) {
            String value = observed.get(key);
            if (value != null) {
                System.out.println(key + "=" + value);
                omitted--;
            }
        }
        System.out.println("omitted_fields=" + omitted);
    }
}
```

Biên dịch và chạy:

```bash
javac DiagnosticDisclosureDemo.java
java DiagnosticDisclosureDemo
```

Stdout **chính xác**:

```text
timestamp.utc=2026-10-29T08:00:00Z
jvm.version=21.0.4
pid=4242
heap.max.bytes=536870912
omitted_fields=4
```

**Điểm cần hiểu từ ví dụ:**

- Chương trình dùng `LinkedHashMap` và `List` có thứ tự đã định, nên thứ tự in ra ổn định. Có tám field đầu vào nhưng chỉ bốn field allowlist được xuất; bốn field bị bỏ **không in cả tên lẫn giá trị**.
- Nếu ngày mai nguồn xuất hiện thêm `session.cookie` hoặc `cloud.secret` thì theo cơ chế này trường mới vẫn bị loại mặc định; không cần biết trước mọi cách đặt tên secret.
- Một field **được cho phép theo tên** vẫn có thể chứa giá trị nhạy cảm do lỗi mapping/nguồn dữ liệu. Ở môi trường thật, cần kiểm tra kiểu dữ liệu, nguồn và nội dung của từng field allowlist, không chỉ dựa trên key.
- PID và phiên bản JVM trong ví dụ được coi là phù hợp với **báo cáo kỹ thuật nội bộ giả định**, **không** có nghĩa luôn được phép công bố công khai. Với người nhận khác, phải dùng allowlist khác và có thể thay PID bằng alias.
- Đây là **bài minh họa về nguyên tắc tối thiểu hóa**, không phải thư viện redaction tổng quát. Nó không parse command line, JSON lồng nhau, URL, log hay heap dump. Không gửi những dữ liệu ấy vào `observed` trong code production nếu không cần thu.

### 7.1 Vì sao dùng allowlist thường an toàn hơn chỉ regex che từ khóa?

Giả sử chương trình in toàn bộ map rồi thay chuỗi có chữ `password`. Nó có thể bỏ sót `Authorization`, `apiKey`, `sessionId`, tên credential tự đặt, token trong URL hoặc giá trị được escape. Nếu nhiều tầng serialize, bí mật còn có thể xuất hiện ở field phụ hoặc trong exception message.

Allowlist trả đúng những trường phục vụ mục tiêu, **mặc định bỏ trường không biết**. Sau allowlist vẫn phải rà soát giá trị, kiểm tra artifact cuối và quyền người nhận. Kết hợp hai lớp sẽ thực tế hơn kỳ vọng một biểu thức chính quy che hết mọi secret trong mọi định dạng.

### 7.2 Khi cần đối chiếu cùng người/host qua nhiều log

Có thể dùng một alias như `user-A`, `host-B`, `session-C` **ổn định trong phạm vi incident** để giữ quan hệ. Mapping từ alias sang giá trị thật phải ở kho nội bộ có quyền hạn chế; không mang mapping vào bản chia sẻ. Không dùng một hash thường của email, số điện thoại hoặc customer ID thấp entropy rồi khẳng định “ẩn danh”: có thể dò ngược bằng từ điển. Nếu cần token hóa/pseudonymization, chọn cơ chế được duyệt, quản lý khóa riêng và xác định rõ thời hạn giữ tính tương quan.

**Ẩn định danh (pseudonymization) không đồng nghĩa ẩn danh tuyệt đối** khi dữ liệu còn có timestamp, vị trí, hành vi hoặc metadata có thể liên kết trở lại.

## 8. Giữ tính hữu ích kỹ thuật sau khi làm sạch

Một bản đã redact quá mạnh có thể khiến người khác không phân biệt được hai JVM hay nguyên nhân runtime. Cần cân bằng giá trị điều tra bằng phương pháp có cấu trúc:

1. **Giữ đơn vị và cửa sổ đo:** “heap used 420 MiB tại 08:00 UTC, max 512 MiB” có ích hơn “memory high”.
2. **Giữ cơ chế kỹ thuật:** loại GC, flags không nhạy cảm, phiên bản Java phù hợp, stack state, exception type, HTTP status; không nhất thiết giữ username/hostname.
3. **Giữ tương quan tối thiểu:** alias `instance-A` và `instance-B`, mốc UTC đã làm tròn nếu có thể, cùng một loại trace trên các phép đo.
4. **Ghi rõ thao tác redaction:** `[REDACTED: credential]`, `[REDACTED: hostname]` hoặc “field omitted by allowlist”. Không thay giá trị thật bằng chuỗi dễ bị hiểu nhầm là dữ liệu đo.
5. **Không làm sai dữ liệu bằng chỉnh sửa tùy tiện:** nếu che một phần stack trace có thể làm mất frame quan trọng, ghi chú rõ frame đã bị ẩn; không đảo thứ tự sự kiện hay xóa sự cố chỉ để số liệu “đẹp”.

Ví dụ, trong điều tra deadlock, giữ thread state, lock ownership relationship và stack frames sau khi loại tên request/customer nếu có. Trong điều tra OOM, retained-size histogram hoặc allocation trends thường đủ cho bước đầu; raw heap dump chỉ dùng khi đã xác định sự cần thiết và kênh bảo vệ.

### 8.1 Lưu raw evidence và bản chia sẻ riêng biệt

Mô hình lưu trữ hợp lý:

```text
Nguồn runtime/process có dữ liệu thực
             |
       thu thập tối thiểu
             |
         raw evidence
 (kho hạn chế quyền + retention)
             |
   phân loại và xuất báo cáo
             |
       redaction + QA
             |
    artifact đã làm sạch
             |
     người nhận phù hợp
```

Giữ raw evidence không phải lúc nào cũng cần hoặc được phép. Nếu không cần để điều tra, đừng tạo bản lưu thừa. Nếu bắt buộc giữ theo quy trình incident, đừng để bản raw vô tình đi cùng bản đã làm sạch trong cùng ZIP, chat attachment hoặc shared folder.

## 9. Một số tình huống chẩn đoán thực tế

### Tình huống A — Hỏi lỗi khởi động sau khi đổi JVM

Cần đưa cho nhóm kỹ thuật: Java major/vendor, loại GC, exception class, stack frames liên quan và cấu hình heap không nhạy cảm. Không cần: toàn bộ `java.class.path` nếu có đường dẫn nội bộ, `System.getProperties()`, biến môi trường, token hay full shell history.

**Bản chia sẻ:** Java version và JVM name (được phép), JVM flags lọc, error type và stack snippet sau khi rà soát message. Nếu stack chứa đường dẫn home/user, dùng path alias có chủ đích.

### Tình huống B — JVM không attach được bằng jcmd

Thông tin hữu ích: phiên bản JDK tool, runtime/vendor, PID namespace, effective user/group mismatch, trạng thái attach support, dạng thông báo lỗi và command đã thử. Không cần paste `env` hoặc toàn bộ command line có credential. Nếu cần chứng minh quyền, có thể chỉ báo “tool chạy dưới account A; process dưới account B” bằng alias.

**Lưu ý:** một lỗi attach có thể do quyền hoặc namespace chứ không phải secret; chia sẻ tối thiểu vẫn đủ chẩn đoán.

### Tình huống C — Production heap tăng liên tục

Thông tin hữu ích: heap occupancy theo thời gian, GC pauses, allocation trend, top object types và retained bytes. Raw heap dump có rủi ro chứa token/request/customer data. Chỉ xuất top class histogram/biểu đồ tổng hợp cho lần trao đổi đầu, nếu dữ liệu class/package nội bộ nhạy cảm thì thay nhóm tên phù hợp.

**Không suy ra** heap dump an toàn chỉ vì file được nén hoặc vì công cụ phân tích chỉ hiển thị vài object trên màn hình.

### Tình huống D — API chậm và log chứa Authorization header

Latency histogram, status code, request duration, dependency duration, trace hierarchy có thể là dữ liệu điều tra hữu ích. Header `Authorization`, cookie, request body hoặc query token không cần để chứng minh CPU/GC pressure. Cần ngăn log capture thừa từ nguồn, sửa cấu hình logging nếu phù hợp và rà soát bản log sẽ gửi.

**Nếu đã lộ secret thật**, thực hiện incident response/rotation theo quy trình; không tiếp tục sao chép giá trị vào báo cáo.

### Tình huống E — Gửi dữ liệu cho cộng đồng hoặc bên thứ ba

Một câu hỏi minh họa đủ tái hiện có thể cung cấp source code rút gọn, stack trace đã xử lý, JDK version và mô tả resource limits bằng số tổng hợp. Không gửi hostname, cloud account ID, image registry private, email hay dump nhị phân gốc chỉ để tăng “đầy đủ”. Hãy thử dựng **minimal reproducible example** với dữ liệu giả trước khi chia sẻ môi trường thật.

## 10. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách xử lý đúng |
| --- | --- | --- |
| “Lệnh chỉ đọc nên output an toàn.” | Output vẫn chứa credential, tên tài khoản, path, dữ liệu nghiệp vụ | Phân loại **nội dung đầu ra**, không dựa vào tính read-only |
| “Chỉ cần ẩn password.” | Bỏ sót token, API key, URL, session cookie, dữ liệu cá nhân | Allowlist + rà soát nhiều loại nhạy cảm |
| “Chỉ hiện dấu *** là xong.” | Raw value còn trong metadata, revision, log khác hoặc file nhúng | Kiểm tra artifact thực, quyền và nguồn dữ liệu sau khi biến đổi |
| “Hash email là đã ẩn danh.” | Giá trị dễ bị dò ngược hoặc liên kết | Loại dữ liệu hoặc dùng pseudonymization được kiểm soát |
| “Heap dump chỉ dành cho debug, không có dữ liệu người dùng.” | Object heap có thể giữ session, token và payload | Bảo vệ như dữ liệu nhạy cảm, ưu tiên báo cáo dẫn xuất |
| “PID/hostname luôn vô hại.” | Lộ topology hoặc giúp ghép lại danh tính | Quyết định theo người nhận và mục đích; dùng alias |
| “Regex không match nghĩa là an toàn.” | Bỏ lọt encoding, nested fields, tên tùy biến, binary | Kiểm tra cấu trúc/định dạng, manual review và test |
| “Cứ đăng toàn bộ stack/log rồi sửa sau.” | Bản sao, notification, cache, history có thể lưu | Làm sạch trước khi chia sẻ; xử lý lộ theo quy trình |
| “Đã bỏ secret thì không cần quan tâm số liệu.” | Mất đơn vị, thứ tự, quan hệ lock/GC gây sai chẩn đoán | Bảo toàn phần kỹ thuật, ghi rõ chỗ bị lược |
| “Ẩn dữ liệu trên màn hình là ẩn khỏi file.” | Text layer, note, revision hoặc metadata còn giá trị | Xuất lại file đã loại dữ liệu thực và verify |

## 11. Checklist trước khi gửi một diagnostic artifact

- [ ] Biết rõ **đối tượng nhận**, kênh chia sẻ và mục đích kỹ thuật.
- [ ] Chỉ thu phần thông tin cần để kiểm chứng giả thuyết; không dump toàn bộ environment/system properties nếu không cần.
- [ ] Đã kiểm tra command line, JVM `-D...`, args, env, URLs, headers, logs và nested fields.
- [ ] Đã đánh giá email/customer/session/request IDs, tên tài khoản, private IP, hostname và các định danh nội bộ.
- [ ] Với JFR, heap dump, core dump, crash report hoặc binary khác, đã xét nguy cơ dữ liệu nằm ngoài những dòng đang hiển thị.
- [ ] Đã chọn **giữ / thay / tổng hợp / loại bỏ** từng nhóm field theo mục đích.
- [ ] Bản chia sẻ vẫn giữ đơn vị, timestamp/scope, Java/JVM context, các sự kiện kỹ thuật cần phân tích.
- [ ] Alias được dùng nhất quán nếu cần correlation; mapping thật không đi kèm bản chia sẻ.
- [ ] Đã rà soát output cuối cùng, file đính kèm, ZIP, metadata, link và permission.
- [ ] Có cách ghi nhận thao tác redaction và nguồn dữ liệu nội bộ nếu cần kiểm chứng lại.
- [ ] Nếu phát hiện secret đã lộ, chuyển sang quy trình phản ứng sự cố phù hợp.

## 12. Bài tập tự đánh giá

**Bài 1 — Chọn trường cần giữ.** Bạn cần xác minh vì sao hai JVM cùng code có pause GC khác nhau. Các trường có sẵn: Java vendor/version, `-Xmx`, GC type, GC event timestamps, full command line, DB password, user email, container CPU quota. Hãy chọn những trường phục vụ so sánh JVM (phiên bản, heap/GC, timestamp, quota) và giải thích vì sao có thể bỏ secret và email; các tham số khác trong command line phải được rà soát riêng.

**Bài 2 — Chọn hình thức chia sẻ.** Một vendor chỉ cần retained-size histogram để tư vấn OOM. Bạn có heap dump, class histogram, raw request payload và một báo cáo heap summary. Ưu tiên histogram/summary đã kiểm tra; raw dump có thể chứa dữ liệu nhạy cảm và chỉ chuyển khi thực sự cần, qua kênh được cấp quyền.

**Bài 3 — Phát hiện giới hạn của sanitizer.** Một chương trình chỉ che chuỗi `password=`. Hãy liệt kê ít nhất bốn trường có thể lọt: `Authorization: Bearer ...`, `apiKey`, token trong URL query, cookie, credential được URL-encode/Base64 hoặc trường nested JSON. Sau đó thiết kế allowlist export phù hợp yêu cầu thay vì mở rộng regex vô hạn.

**Bài 4 — Kiểm tra lại bản chia sẻ.** File báo cáo HTML hiển thị `[REDACTED]` nhưng source vẫn có giá trị thật trong thuộc tính data-*; screenshot còn hostname trên tab trình duyệt; ZIP đính kèm gồm raw heap dump. Kết luận: redaction **chưa đạt** vì người nhận vẫn truy cập được dữ liệu nhạy cảm qua artifact cuối.

## Tài liệu tham khảo

- [Java SE 21 — ProcessHandle.Info](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): các trường `Optional` của thông tin tiến trình, tùy quyền và OS.
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic commands và giới hạn quyền/khả năng hỗ trợ, bao gồm những lệnh có thể tiết lộ system properties/command line.
- [JDK 21 — jps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html): liệt kê JVM và các tùy chọn hiện JVM arguments.
- [JDK 21 — JFR Runtime Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): tham khảo cơ chế ghi sự kiện JFR; loại event và thông tin cần đánh giá theo recording thực tế.

**Ghi nhớ:** “Thông tin có sẵn” trả lời câu hỏi *tool có thể đọc gì trong phạm vi được phép*. “Thông tin có thể chia sẻ” trả lời câu hỏi *ai cần dữ liệu gì, với mức độ chi tiết nào*. Với Java runtime diagnostics, hãy **giới hạn thu thập từ nguồn, phân loại theo người nhận, xuất allowlist, kiểm tra artifact đã làm sạch** và giữ dữ liệu nhạy cảm trong kênh được bảo vệ. Một báo cáo chẩn đoán hữu ích phải đủ bằng chứng kỹ thuật mà không mang theo credential, dữ liệu cá nhân hay môi trường nội bộ không cần thiết.