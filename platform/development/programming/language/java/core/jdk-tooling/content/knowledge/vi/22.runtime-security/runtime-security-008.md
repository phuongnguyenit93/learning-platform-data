# Secret trong tham số của ứng dụng Java

Secret là dữ liệu nhạy cảm mà ứng dụng cần dùng để xác thực, ký, mã hóa hoặc truy cập dịch vụ, chẳng hạn password, API token, database credential, OAuth client secret, private key và encryption key. “Secret trong tham số” có thể nói tới secret được truyền qua tham số dòng lệnh/JVM, hoặc secret được truyền làm tham số cho một method Java.

Hai vị trí này có rủi ro khác nhau. Tham số dòng lệnh có thể xuất hiện trong process listing, shell history, công cụ giám sát hoặc log của CI. Tham số method nằm trong bộ nhớ của tiến trình; cách biểu diễn và thời gian giữ secret trong bộ nhớ quyết định mức độ lộ lọt khi có log, heap dump, crash dump hoặc lỗi xử lý.

Bài này sử dụng JDK 17 trở lên. Mục tiêu là đưa secret vào ứng dụng qua kênh phù hợp, giữ secret trong bộ nhớ trong thời gian ngắn, không ghi secret vào log và xóa các buffer có thể sửa được sau khi sử dụng.

## 1. Nhận diện secret và dữ liệu không nhạy cảm

Không phải mọi tham số đều là secret. Hãy phân loại trước khi chọn cách truyền.

| Dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Password | Mật khẩu database hoặc keystore | Secret; không đưa vào command line hoặc log |
| API token | Bearer token gọi dịch vụ | Secret; giới hạn scope và thời hạn |
| Private key | Khóa ký hoặc khóa TLS | Secret đặc biệt quan trọng; giữ trong keystore/HSM |
| Encryption key | Khóa AES dùng mã hóa dữ liệu | Secret; quản lý vòng đời và quyền truy cập |
| Client secret | OAuth client credential | Secret; không commit vào source |
| Username | Tên tài khoản | Có thể nhạy cảm theo ngữ cảnh; thường không đủ để xác thực một mình |
| Hostname/port | `db.internal:5432` | Thường là cấu hình, không phải secret |
| File path | Đường dẫn tới keystore | Thường là cấu hình; quyền truy cập file vẫn quan trọng |

Một secret cần được bảo vệ trong toàn bộ vòng đời: lúc lưu, truyền, nạp vào tiến trình, sử dụng, ghi log, backup, rotate và thu hồi.

## 2. Vì sao không truyền secret bằng tham số dòng lệnh?

Ví dụ sau là cách truyền không an toàn:

~~~text
java -jar app.jar --password ...
~~~

Dấu ba chấm ở đây chỉ biểu thị giá trị secret, không phải giá trị cần nhập. Khi secret nằm trong command line, nó có thể bị lộ qua:

- Process listing hoặc công cụ quản trị tiến trình. Khả năng xem phụ thuộc hệ điều hành, quyền user và cấu hình máy.
- Shell history nếu người dùng nhập lệnh trực tiếp.
- Log của CI/CD, deployment script, task scheduler hoặc hệ thống giám sát.
- Báo cáo lỗi và diagnostic thu thập command line.
- Script wrapper vô tình in lại toàn bộ đối số.

Không phải mọi user trên mọi hệ điều hành đều đọc được command line của mọi tiến trình. Tuy nhiên, vì nhiều công cụ quản trị và pipeline có thể ghi nhận tham số, không nên dựa vào giới hạn hiển thị của một hệ điều hành để bảo vệ secret.

Trong Java, `main(String[] args)` nhận các đối số này dưới dạng chuỗi. Java không tự che hoặc mã hóa chúng:

~~~java
public static void main(String[] args) {
    // args chứa nguyên văn các đối số mà launcher đã truyền.
}
~~~

Không truyền password, API token, private key hoặc credential qua `args`. Dùng command line cho thông tin không nhạy cảm như tên môi trường, chế độ chạy, đường dẫn cấu hình hoặc port.

## 3. Không đặt secret trong JVM system property

Một biến thể khác là truyền secret qua `-D`:

~~~text
java -Dapp.password=... -jar app.jar
~~~

Giá trị system property có thể được đọc trong ứng dụng:

~~~java
String password = System.getProperty("app.password");
~~~

Cách này không bảo vệ secret. Giá trị `-D` vẫn nằm trong JVM command line và có thể được đọc từ `System.getProperties()` trong tiến trình. Diagnostic, log cấu hình hoặc code debug cũng có thể vô tình in system properties.

Dùng system properties cho cấu hình không bí mật như profile, locale hoặc tên môi trường. Không dùng chúng để chứa password, token, private key hoặc encryption key.

## 4. Environment variable có an toàn tuyệt đối không?

Environment variable thường tiện cho container, service và pipeline:

~~~powershell
$env:APP_MODE = "production"
java -jar app.jar
~~~

Trong Java, đọc biến môi trường bằng:

~~~java
String mode = System.getenv("APP_MODE");
~~~

Tuy nhiên, environment variable không phải secret manager:

- Biến môi trường được kế thừa bởi process con nếu không loại bỏ.
- Người có quyền phù hợp có thể đọc environment của tiến trình hoặc cấu hình runtime.
- CI runner, crash report, debug output hoặc script có thể ghi lại giá trị.
- Biến thường tồn tại trong môi trường của tiến trình trong suốt vòng đời ứng dụng.

Một số nền tảng quản lý container có cơ chế secret và kiểm soát quyền tốt hơn việc tự đặt biến môi trường. Hãy hiểu rõ cách nền tảng lưu, inject, hiển thị và rotate giá trị.

Environment variable có thể dùng làm cầu nối trong một số hệ thống đã được kiểm soát, nhưng không nên xem nó là kho lưu trữ bí mật có bảo đảm. Ưu tiên secret manager hoặc file secret được mount với quyền truy cập hạn chế.

## 5. Các cách đưa secret vào ứng dụng

Chọn kênh theo cách ứng dụng chạy:

| Cách truyền | Trường hợp phù hợp | Lưu ý |
|---|---|---|
| `Console.readPassword()` | Chạy tương tác tại terminal | Không echo ký tự nhập; cần console |
| Secret manager | Ứng dụng server, cloud, production | Dùng identity của workload và quyền tối thiểu |
| File secret được bảo vệ | Container hoặc service có secret volume | Giới hạn quyền file; không commit file vào source |
| Standard input (stdin) | Script hoặc tiến trình cha truyền secret cho tiến trình con | Secret không nằm trong command arguments; child phải đọc stdin |
| Environment variable | Hệ thống triển khai đã có chính sách quản lý phù hợp | Có thể bị kế thừa hoặc đọc qua process inspection |
| Java method parameter | Truyền secret giữa các thành phần trong cùng tiến trình | Giảm thời gian sống; tránh tạo bản sao không cần thiết |

Không có một kênh duy nhất phù hợp cho mọi môi trường. Một ứng dụng CLI tương tác có thể dùng `Console.readPassword`; một service chạy không có terminal nên lấy secret từ secret manager hoặc file được mount.

## 6. Nhập password tương tác bằng Console.readPassword

`System.console()` trả về đối tượng `Console` nếu tiến trình có console tương tác. `readPassword()` đọc password mà không hiển thị các ký tự người dùng nhập và trả về `char[]`.

Ví dụ:

~~~java
import java.io.Console;
import java.util.Arrays;

public final class SecretParameterDemo {
    public static void main(String[] args) {
        if (args.length != 0) {
            System.err.println("Do not pass secrets as command-line arguments.");
            return;
        }

        Console console = System.console();
        if (console == null) {
            System.err.println("No interactive console; use a protected secret source.");
            return;
        }

        char[] secret = console.readPassword("Enter secret: ");
        if (secret == null) {
            System.err.println("No secret was supplied.");
            return;
        }

        try {
            processSecret(secret);
        } finally {
            Arrays.fill(secret, (char) 0);
        }
    }

    private static void processSecret(char[] secret) {
        if (secret.length == 0) {
            throw new IllegalArgumentException("Secret must not be empty.");
        }

        // Thay phần này bằng thao tác xác thực thực tế.
        // Không chuyển secret thành String và không ghi giá trị ra log.
        System.out.println("Secret passed to the processing method.");
    }
}
~~~

Biên dịch và chạy trên terminal:

~~~powershell
javac SecretParameterDemo.java
java SecretParameterDemo
~~~

Khi chạy, terminal hiển thị prompt `Enter secret:` nhưng không echo nội dung được gõ. Sau khi method xử lý kết thúc, `finally` ghi đè các phần tử trong mảng.

Stdout sau khi nhập một secret bất kỳ:

~~~text
Secret passed to the processing method.
~~~

Thông báo không chứa giá trị secret. Method `processSecret` trong ví dụ chỉ minh họa việc nhận tham số; hãy thay bằng thao tác xác thực thực tế của ứng dụng.

### Khi nào System.console() là null?

`System.console()` có thể trả về `null` khi ứng dụng chạy trong IDE, service, một số môi trường container, pipeline hoặc khi standard input/output được redirect. Không nên giả định mọi tiến trình Java đều có terminal.

Nếu không có console, dùng secret manager, protected file hoặc một kênh input được thiết kế cho môi trường non-interactive. Tránh fallback tự động sang command-line argument hoặc system property.

## 7. Truyền secret giữa các method

Secret thường được lấy ở một lớp rồi chuyển tới lớp thực hiện thao tác. Hãy truyền bằng tham số rõ ràng thay vì đặt vào biến global hoặc system property.

Ví dụ chữ ký method:

~~~java
private static void authenticate(char[] password) {
    // Dùng password với API xác thực.
}
~~~

Các nguyên tắc:

- Chỉ truyền secret tới method thực sự cần nó.
- Không đặt secret vào field static hoặc singleton nếu không cần giữ lâu.
- Tránh lưu secret trong object sống lâu hoặc cache.
- Không tạo thêm bản sao nếu API có thể nhận buffer hiện có.
- Xác định rõ method nào sở hữu buffer và method nào chịu trách nhiệm xóa.
- Không ghi tham số secret vào log, exception message hoặc `toString()`.

Nếu method chỉ mượn buffer để thực hiện thao tác, caller thường chịu trách nhiệm xóa sau khi method trả về. Nếu method nhận quyền sở hữu buffer, cần quy định rõ việc xóa trong contract để không có hai nơi cùng xóa khi một bên vẫn còn dùng.

## 8. Vì sao nên cân nhắc char[] thay cho String?

`String` là immutable: sau khi tạo, nội dung của nó không thể được ghi đè qua API thông thường. Khi không còn tham chiếu, thời điểm object được garbage collector thu hồi không được bảo đảm. Vì vậy, ứng dụng không thể chủ động xóa nội dung một `String` khỏi bộ nhớ.

`char[]` là mutable. Sau khi sử dụng, ứng dụng có thể ghi đè từng phần tử:

~~~java
Arrays.fill(password, (char) 0);
~~~

Một số API Java bảo mật nhận `char[]`, ví dụ:

- `Console.readPassword()` trả về `char[]`.
- `KeyStore.load(InputStream, char[])` nhận mật khẩu keystore.
- `KeyStore.getKey(String, char[])` nhận mật khẩu bảo vệ key entry.

Ví dụ nạp PKCS12 keystore bằng password từ console:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;

Console console = System.console();
if (console == null) {
    throw new IllegalStateException("An interactive console is required.");
}

char[] storePassword = console.readPassword("Keystore password: ");
if (storePassword == null) {
    throw new IllegalStateException("No password was supplied.");
}

try {
    KeyStore keyStore = KeyStore.getInstance("PKCS12");
    try (InputStream input = Files.newInputStream(Path.of("server.p12"))) {
        keyStore.load(input, storePassword);
    }
    System.out.println("Keystore loaded.");
} finally {
    Arrays.fill(storePassword, (char) 0);
}
~~~

`char[]` giảm khả năng giữ secret lâu trong một immutable object, nhưng không tạo ra bảo đảm xóa tuyệt đối. API có thể tạo bản sao nội bộ; runtime, JIT, heap dump hoặc native code có thể tạo thêm bản sao. Hãy kết hợp với quyền truy cập tiến trình, giới hạn thời gian sống và kiểm soát dump/log.

Không chuyển `char[]` thành `String` chỉ để truyền tiện hơn:

~~~java
String passwordText = new String(storePassword);
~~~

Cách này tạo một bản sao immutable mà ứng dụng không thể chủ động ghi đè.

## 9. Dùng byte[] cho secret dạng byte

Một số khóa mã hóa và token được xử lý dưới dạng byte. Trong trường hợp đó, dùng `byte[]` nếu API đích nhận byte buffer.

Ví dụ xóa buffer sau khi dùng:

~~~java
byte[] keyMaterial = obtainKeyMaterial();

try {
    useKeyMaterial(keyMaterial);
} finally {
    Arrays.fill(keyMaterial, (byte) 0);
}
~~~

Không giả định mọi secret đều là văn bản UTF-8. Encryption key là dữ liệu byte; chuyển tùy tiện qua `String` có thể làm thay đổi dữ liệu hoặc tạo thêm bản sao khó xóa.

`Arrays.fill` chỉ ghi đè mảng mà ứng dụng đang giữ. Nó không đảm bảo xóa bản sao do thư viện, JVM, garbage collector, hệ điều hành hoặc thiết bị native tạo ra. Với yêu cầu bảo mật cao, dùng API quản lý khóa như keystore/HSM thay vì tự cầm raw key trong ứng dụng.

## 10. Lưu secret trong file được bảo vệ

Một số runtime cấp secret qua file được mount, ví dụ secret volume trong container. Ứng dụng đọc file bằng đường dẫn cấu hình không bí mật.

Ví dụ đọc secret dạng byte:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

Path secretPath = Path.of("/run/secrets/service-token");
byte[] token = Files.readAllBytes(secretPath);

try {
    callService(token);
} finally {
    Arrays.fill(token, (byte) 0);
}
~~~

Đây là snippet minh họa; method `callService` thuộc ứng dụng cần được triển khai. Không in nội dung file ra log.

Với file secret:

- Giới hạn quyền đọc cho đúng tài khoản chạy ứng dụng.
- Tránh đặt file trong thư mục source, web root hoặc thư mục chia sẻ công khai.
- Không đưa file vào Git, image layer hoặc artifact build.
- Dùng cơ chế mount/rotation của nền tảng để thay secret.
- Không copy secret sang file tạm không được bảo vệ.
- Kiểm tra quyền file và quyền thư mục cha, không chỉ tên đường dẫn.

Trên Linux, quyền file có thể được giới hạn bằng ACL hoặc mode phù hợp; trên Windows, dùng NTFS ACL. Quyền chính xác phụ thuộc tài khoản service và cách triển khai.

## 11. Truyền secret cho tiến trình con bằng stdin

Nếu Java cần gọi một công cụ khác, không đặt secret trong đối số `ProcessBuilder`:

~~~java
new ProcessBuilder("some-tool", "--token", secretText).start();
~~~

Cách này đưa token vào command line của tiến trình con.

Nếu công cụ hỗ trợ đọc secret từ stdin, khởi chạy nó mà không có secret trong arguments rồi ghi secret vào standard input:

~~~java
Process process = new ProcessBuilder("credential-aware-tool").start();

try (var childInput = process.getOutputStream()) {
    childInput.write(secretBytes);
    childInput.write('\n');
}
~~~

Đoạn này chỉ phù hợp khi công cụ con có giao thức đọc secret từ stdin. Cần xác định encoding và định dạng kết thúc dòng theo giao thức của công cụ. Sau khi ghi, đóng stream để báo EOF nếu giao thức yêu cầu.

Stdin tránh đưa secret vào process arguments nhưng không biến dữ liệu thành an toàn tuyệt đối: tiến trình con vẫn nhận được secret và có thể ghi nó ra log hoặc bộ nhớ. Chỉ gọi executable đáng tin cậy, giới hạn quyền của child process và xóa buffer ở caller khi hoàn tất.

## 12. Secret manager và workload identity

Trong môi trường production, secret manager thường là lựa chọn phù hợp hơn việc tự lưu mật khẩu trong file cấu hình. Ứng dụng xác thực với dịch vụ quản lý secret bằng workload identity hoặc cơ chế credential ngắn hạn, rồi lấy secret cần dùng.

Một luồng điển hình:

1. Platform cấp identity cho workload.
2. Ứng dụng xác thực với secret manager bằng identity đó.
3. Secret manager kiểm tra policy và trả secret mà workload được phép đọc.
4. Ứng dụng sử dụng secret trong thời gian cần thiết.
5. Buffer được xóa khi có thể; secret được rotate theo policy.
6. Khi workload không còn cần quyền, policy được thu hồi.

Các nguyên tắc thiết kế:

- Cấp quyền tối thiểu theo secret và môi trường.
- Dùng identity riêng cho từng workload thay vì một token dùng chung.
- Ưu tiên credential ngắn hạn và tự động rotate.
- Không ghi response của secret manager vào log.
- Cache secret chỉ khi cần; đặt TTL và kế hoạch refresh.
- Có cơ chế xử lý khi secret hết hạn hoặc bị thu hồi.
- Không nhúng bootstrap secret lâu dài vào image hoặc source code.

Tên API và cách tích hợp phụ thuộc nhà cung cấp cloud/secret manager. Không hard-code một credential tĩnh để lấy credential tĩnh khác nếu nền tảng đã hỗ trợ workload identity.

## 13. Không để secret rò rỉ qua log và exception

Một secret có thể được truyền đúng cách nhưng vẫn bị lộ sau đó.

Tránh:

~~~java
logger.info("Using API token: {}", token);
throw new IllegalStateException("Authentication failed for token " + token);
~~~

Nên ghi sự kiện không chứa giá trị bí mật:

~~~java
logger.warn("Authentication failed for service account {}", accountId);
~~~

`accountId` cũng cần được đánh giá theo chính sách riêng tư của hệ thống. Khi cần correlation, dùng request ID hoặc một định danh không chứa secret.

Kiểm tra các nơi có thể thu thập dữ liệu:

- Application log và structured log.
- HTTP request/response logging.
- APM, tracing và telemetry.
- Exception message và stack trace có custom context.
- CI/CD output và deployment logs.
- Heap dump, core dump và crash report.
- Debug endpoint, actuator hoặc diagnostic snapshot.

Không đưa secret vào `toString()`, record component, exception constructor hoặc object được serialize tự động. Tránh bật wire-level logging cho request chứa credential trên môi trường production.

## 14. Secret trong source code, cấu hình và repository

Không hard-code secret:

~~~java
private static final String API_TOKEN = "...";
~~~

Không đặt secret trong:

- Git repository, kể cả repository private.
- File `.properties`, YAML hoặc JSON được commit.
- Dockerfile, build script hoặc command history.
- Unit test snapshot và fixture được chia sẻ.
- Tài liệu, ticket hoặc screenshot.
- Build artifact và image layer.

Nếu secret đã được commit, xóa dòng đó chưa đủ vì giá trị có thể còn trong Git history, clone, cache hoặc artifact. Hãy thu hồi/rotate secret trước, sau đó xử lý lịch sử repository theo quy trình của tổ chức.

Cấu hình nên chứa tên secret hoặc tham chiếu tới secret manager, ví dụ tên credential hoặc đường dẫn mount; secret value được cung cấp tại runtime.

## 15. Xử lý vòng đời và rotation

Secret không nên tồn tại mãi. Xây dựng vòng đời rõ ràng:

1. **Create:** sinh secret bằng công cụ hoặc dịch vụ đáng tin cậy.
2. **Store:** lưu trong secret manager, keystore hoặc kho được bảo vệ.
3. **Grant:** cấp quyền cho workload cần sử dụng.
4. **Use:** nạp secret trong thời gian ngắn và không log giá trị.
5. **Rotate:** thay secret theo lịch hoặc khi có dấu hiệu rò rỉ.
6. **Revoke:** thu hồi secret cũ sau khi các consumer chuyển đổi.
7. **Audit:** theo dõi ai hoặc workload nào đã truy cập secret.

Khi rotate, cần hỗ trợ giai đoạn chuyển tiếp nếu dịch vụ cho phép hai credential cùng hợp lệ. Không xóa credential cũ trước khi xác nhận consumer đã dùng credential mới, trừ trường hợp khẩn cấp cần thu hồi ngay.

Nếu secret bị lộ:

- Thu hồi hoặc rotate ngay theo mức độ rủi ro.
- Kiểm tra log và hệ thống truy cập liên quan.
- Xác định phạm vi dịch vụ, dữ liệu và workload bị ảnh hưởng.
- Loại secret khỏi nơi lưu trữ/log theo quy trình xử lý sự cố.
- Tạo secret mới với quyền tối thiểu.
- Ghi nhận sự cố mà không sao chép lại secret vào báo cáo.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Secret xuất hiện trong process listing | Được truyền qua `args` hoặc JVM `-D` | Loại secret khỏi command line; dùng secret manager, file bảo vệ hoặc stdin |
| Secret xuất hiện trong shell history | Nhập giá trị trực tiếp trong command | Không nhập secret literal; dùng prompt hoặc secret injection được bảo vệ |
| `System.console()` trả về `null` | Chạy trong IDE, service hoặc tiến trình không có terminal | Dùng secret manager hoặc file secret được mount |
| Secret xuất hiện trong log | Logger, exception hoặc `toString()` in tham số | Redact dữ liệu, sửa logging và kiểm tra pipeline log |
| Secret còn trong object sau xử lý | Dùng `String` hoặc giữ tham chiếu lâu | Ưu tiên `char[]`/`byte[]` khi API hỗ trợ; giới hạn scope và xóa buffer |
| Process con không nhận secret từ stdin | Công cụ con không hỗ trợ giao thức stdin mong đợi | Kiểm tra tài liệu công cụ; dùng IPC/secret mechanism được hỗ trợ |
| Ứng dụng không đọc được secret file | Sai mount path hoặc ACL/permission | Kiểm tra quyền user service và cấu hình mount |
| Secret mới không có hiệu lực | Cache chưa refresh hoặc consumer còn dùng giá trị cũ | Xây dựng TTL, refresh và rollout theo quy trình rotation |
| Credential bị từ chối sau rotation | Credential cũ đã bị thu hồi trước khi consumer chuyển đổi | Điều phối thời gian chuyển tiếp hoặc xử lý thu hồi khẩn cấp |
| Heap dump chứa dữ liệu nhạy cảm | Secret còn sống trong heap khi dump được tạo | Hạn chế dump access, giảm lifetime và bảo vệ nơi lưu dump |

## 17. Checklist thiết kế tham số chứa secret

- [ ] Secret không nằm trong command-line arguments.
- [ ] Secret không nằm trong JVM system properties.
- [ ] Environment variable chỉ được dùng khi nền tảng có chính sách bảo vệ phù hợp.
- [ ] Đã chọn secret manager, protected file, stdin hoặc console phù hợp với runtime.
- [ ] Method chỉ nhận secret qua tham số khi thực sự cần.
- [ ] Dùng `char[]` hoặc `byte[]` khi API hỗ trợ và có thể xóa buffer.
- [ ] Đã quy định rõ quyền sở hữu và trách nhiệm xóa buffer.
- [ ] Không chuyển secret thành `String` không cần thiết.
- [ ] Không ghi secret vào log, exception, `toString()` hoặc telemetry.
- [ ] File secret có ACL/quyền đọc hạn chế.
- [ ] Process con không nhận secret trong arguments hoặc environment ngoài nhu cầu.
- [ ] Secret có scope tối thiểu, thời hạn phù hợp và quy trình rotation.
- [ ] Heap dump, crash dump, CI logs và backup được bảo vệ.
- [ ] Có quy trình thu hồi và xử lý khi secret bị lộ.

Secret trong tham số cần được bảo vệ cả khi truyền vào tiến trình lẫn khi chuyển giữa các method. Tránh command-line arguments và JVM system properties vì chúng dễ xuất hiện trong diagnostic hoặc log; chọn console, secret manager, protected file hoặc stdin theo môi trường. Trong Java, chỉ truyền secret tới thành phần cần dùng, ưu tiên buffer có thể xóa khi API hỗ trợ, giới hạn thời gian sống và tuyệt đối không ghi giá trị vào log. Cuối cùng, thiết kế quyền truy cập, rotation và thu hồi để secret được bảo vệ trong toàn bộ vòng đời.

## Tài liệu tham khảo

- Oracle, Java SE 17 API — `Console.readPassword`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html#readPassword(java.lang.String,java.lang.Object...)
- Oracle, Java SE 17 API — `KeyStore.load`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html#load(java.io.InputStream,char[])
- Oracle, Java SE 17 API — `ProcessBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Oracle, Java SE 17 API — `Arrays.fill`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#fill(char[],char)
- Oracle, Java SE 17 API — `System.getenv`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#getenv()
