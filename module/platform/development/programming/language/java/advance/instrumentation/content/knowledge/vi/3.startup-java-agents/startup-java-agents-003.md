# `-javaagent:jarpath[=options]` và cách nhận chuỗi `agentArgs`

Một **Java agent khi khởi động** là mã được JVM nạp và gọi trước phương thức `main` của ứng dụng. Điểm bắt đầu của startup agent là phương thức `premain`. Cách phổ biến để khai báo agent cho một tiến trình Java là tùy chọn JVM `-javaagent`, trong đó đường dẫn chỉ tới **agent JAR** và phần sau dấu `=` là cấu hình riêng của agent.

Bài này tập trung vào cách JVM nhận tùy chọn `-javaagent:jarpath=options`, cách chuyển `options` thành tham số `String agentArgs`, cách khai báo `Premain-Class` trong manifest, và cách tự viết, đóng gói, chạy thử một startup agent độc lập bằng Java 17+. Ví dụ chỉ kiểm tra cơ chế khởi động và truyền tham số; nó chưa biến đổi bytecode.

## 1. Cú pháp chính xác và ý nghĩa từng thành phần

Cú pháp đầy đủ là:

~~~text
-javaagent:<jarpath>[=<options>]
~~~

Dấu ngoặc vuông chỉ **phần tùy chọn** trong tài liệu; không gõ dấu `[` và `]` khi thực thi.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `-javaagent:` | Tùy chọn JVM để nạp agent khi khởi động | `-javaagent:` |
| `<jarpath>` | Đường dẫn tương đối hoặc tuyệt đối đến agent JAR đã đóng gói đúng | `agent-demo.jar` |
| `=` sau đường dẫn | Phân cách đường dẫn JAR với chuỗi cấu hình agent | `agent-demo.jar=` |
| `<options>` | **Một chuỗi** do chính agent định nghĩa ngữ nghĩa và cú pháp | `mode=trace,sample=25` |

Ví dụ hoàn chỉnh khi chạy ứng dụng tên `Application`:

~~~bash
java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue
~~~

JVM hiểu đây là hai nhóm dữ liệu khác nhau:

- Agent JAR: `agent-demo.jar`.
- Chuỗi agent được truyền đến `premain`: `mode=trace,sample=25`.
- Lớp main của ứng dụng: `Application`; `main(String[] args)` nhận đúng hai đối số là `red` và `blue`.

`-javaagent` là **tùy chọn của chương trình khởi chạy Java**, nên phải đặt ở vị trí dành cho JVM options, **trước** tên lớp chính hoặc `-jar app.jar`. Phần sau tên lớp chính/`-jar app.jar` là tham số ứng dụng: nếu đặt `-javaagent:...` ở đó, ứng dụng có thể chỉ nhận nó như một chuỗi trong `main(args)` và agent sẽ không được kích hoạt theo cách mong muốn.

Cú pháp `-javaagent` không đồng nghĩa `-jar`:

- `-javaagent:agent.jar` chỉ tới JAR có **`Premain-Class`** để JVM gọi `premain`.
- `-jar app.jar` chỉ tới executable JAR có **`Main-Class`** (hoặc cơ chế launcher tương ứng) để gọi ứng dụng.
- `-cp` hoặc `--class-path` xác định classpath cho lớp ứng dụng; nó không thay thế `-javaagent` và không tự bật `premain`.

Ví dụ startup agent chạy cùng một executable application JAR:

~~~bash
java -javaagent:agent-demo.jar=mode=trace,sample=25 -jar application.jar
~~~

`application.jar` trong lệnh trên chỉ mang tính minh họa: nó phải là JAR ứng dụng chạy được, và `agent-demo.jar` phải là agent JAR được đóng gói hợp lệ.

## 2. JVM gọi `premain` ở giai đoạn nào?

Luồng khái quát:

~~~text
Lệnh java
    |
    +-- JVM launcher phân tích -javaagent:jarpath[=options]
    |
    +-- JVM tìm agent JAR và đọc main manifest
    |       |
    |       +-- Premain-Class: tên lớp agent
    |
    +-- JVM nạp lớp agent, gọi premain(agentArgs, instrumentation)
    |       |
    |       +-- Agent đọc cấu hình và khởi tạo hook/transformer (nếu có)
    |
    +-- premain trả về
    |
    +-- Ứng dụng bắt đầu main(String[] args)
~~~

`premain` được gọi **trước `main` của ứng dụng**, không có nghĩa nó chạy trước mọi hoạt động khởi tạo JVM hoặc trước tất cả class loading của JVM. Các lớp cần cho launcher/agent có thể đã được nạp. Vì thế, nếu sau này muốn gắn `ClassFileTransformer`, phải cân nhắc thời điểm lớp mục tiêu được load và khả năng retransform phù hợp.

Lớp khai báo trong `Premain-Class` cần có một trong hai chữ ký:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

hoặc:

~~~java
public static void premain(String agentArgs)
~~~

Cả hai phải là phương thức `public static` trả về `void`. JVM **ưu tiên** biến thể hai tham số nếu có, rồi mới thử biến thể một tham số. Đối tượng `Instrumentation` do JVM cấp để agent truy cập khả năng instrumentation (như đăng ký transformer); người chạy lệnh không truyền đối tượng này qua CLI. Có thể chỉ dùng biến thể một tham số nếu agent không cần API đó, nhưng biến thể hai tham số thường hữu ích hơn cho instrumentation thực tế.

Nếu không tìm thấy JAR, không có `Premain-Class` hợp lệ, không nạp được lớp/phương thức `premain`, hoặc `premain` ném ngoại lệ không được xử lý, việc khởi động có thể bị hủy **trước khi `main` chạy**. Đừng thiết kế startup agent giả định rằng tất cả lỗi cấu hình sẽ được ứng dụng bắt lại sau khi vào `main`.

Lưu ý phân biệt: `agentmain` là điểm vào của agent được nạp vào JVM **đang chạy** (khi cơ chế đó được hỗ trợ). Khi kích hoạt bằng `-javaagent` lúc startup, JVM gọi `premain`; không gọi `agentmain` để thay thế.

## 3. `agentArgs` thực sự chứa gì?

Phần `<options>` được truyền đến `premain` dưới dạng **một `String` duy nhất**. JVM không tự biến dấu phẩy thành danh sách, không giải mã cặp `key=value`, không kiểm tra `mode` hay `sample`, và không tự xây dựng một `Map`. Mọi quy ước tách chuỗi, giá trị mặc định, kiểm tra kiểu và xử lý lỗi là trách nhiệm của agent.

| Cách gọi | Giá trị mà agent cần hiểu |
| --- | --- |
| `-javaagent:agent-demo.jar=mode=trace,sample=25` | Một chuỗi `"mode=trace,sample=25"` |
| `-javaagent:agent-demo.jar=hello=world` | Một chuỗi `"hello=world"`; dấu `=` bên trong options thuộc về dữ liệu |
| `-javaagent:agent-demo.jar` | Không có phần `=options`; code phải xử lý trường hợp không có cấu hình |
| `-javaagent:agent-demo.jar=` | Có dấu `=` nhưng chuỗi options rỗng |
| `-javaagent:agent-demo.jar=mode=trace` | Một chuỗi `"mode=trace"`, **không** phải một tham số bổ sung của `main` |

Trên OpenJDK/HotSpot 21, khi không viết `=options` thì `agentArgs` là `null`; khi viết `=` nhưng không có gì theo sau thì là chuỗi rỗng `""`. Ví dụ ở phần sau được chạy kiểm tra theo hành vi này. Không nên buộc logic ứng dụng phụ thuộc vào việc phân biệt hai trạng thái nếu cả hai cùng có nghĩa là "dùng mặc định": xử lý **cả `null` lẫn chuỗi rỗng**.

Để hình dung chính xác điểm nối dữ liệu:

~~~text
java -javaagent:agent-demo.jar=mode=trace,sample=25 Application red blue
               |--------------------|             |------|
                  agentArgs (1 String)            main(args) (2 Strings)
~~~

Trong minh họa trên, `Application` phải nằm trên classpath; câu lệnh chạy độc lập đầy đủ sẽ có `-cp .` như ví dụ chính.

Một số phân biệt hay nhầm:

- `System.getProperty("mode")` không tự đọc `mode=trace` trong `agentArgs`. Chỉ khi truyền `-Dmode=trace` riêng thì mới có JVM system property tương ứng.
- Biến môi trường và application arguments không tự trở thành `agentArgs`.
- Nếu chạy nhiều startup agents, mỗi lần `-javaagent` có một chuỗi options **riêng** gửi cho `premain` của agent đó.
- Các dấu `,`, `;`, `:`, `=` bên trong options không có cùng nghĩa ở mọi agent. Ngữ pháp chỉ tồn tại khi tác giả agent quy định rõ.

## 4. Ví dụ chạy được với Java 17+: agent nhận và phân tích `agentArgs`

Ta tạo ba file đặt **cùng một thư mục**. Lớp agent in nguyên chuỗi nhận được, rồi tự phân tích quy ước đơn giản `mode=<off|trace>,sample=<0..100>`. Lớp ứng dụng chỉ in các đối số `main` để chứng minh hai đường truyền tách biệt.

### 4.1. Tệp `StartupAgent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.LinkedHashMap;
import java.util.Map;

public final class StartupAgent {
    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("[agent] raw=" + agentArgs);

        Map<String, String> options = parse(agentArgs);
        String mode = options.getOrDefault("mode", "off");
        int sample = Integer.parseInt(options.getOrDefault("sample", "10"));

        if (!mode.equals("off") && !mode.equals("trace")) {
            throw new IllegalArgumentException("mode must be off or trace");
        }
        if (sample < 0 || sample > 100) {
            throw new IllegalArgumentException("sample must be 0..100");
        }

        System.out.println("[agent] mode=" + mode + ", sample=" + sample
                + ", instrumentation=" + (instrumentation != null));
    }

    private static Map<String, String> parse(String raw) {
        Map<String, String> parsed = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) {
            return parsed;
        }

        for (String item : raw.split(",", -1)) {
            int equalsAt = item.indexOf('=');
            if (equalsAt < 1 || equalsAt == item.length() - 1) {
                throw new IllegalArgumentException("expected key=value: " + item);
            }

            String key = item.substring(0, equalsAt);
            String value = item.substring(equalsAt + 1);

            if (!key.equals("mode") && !key.equals("sample")) {
                throw new IllegalArgumentException("unknown option: " + key);
            }
            if (parsed.putIfAbsent(key, value) != null) {
                throw new IllegalArgumentException("duplicate option: " + key);
            }
        }
        return parsed;
    }
}
~~~

Điểm cần đọc kỹ:

1. JVM đưa nguyên `agentArgs` vào `premain`; lệnh in `[agent] raw=...` diễn ra **trước khi tự tách chuỗi**.
2. `parse` là logic do ví dụ **tự chọn**: tách theo dấu phẩy, rồi theo **dấu `=` đầu tiên** của mỗi mục. Không phải quy tắc bắt buộc của Java agent.
3. Khi `agentArgs` là `null` hoặc chuỗi rỗng, `parse` trả map rỗng; `mode=off` và `sample=10` là mặc định **do ví dụ đặt**, không phải JVM mặc định.
4. `Integer.parseInt` chỉ nhận chuỗi số nguyên phù hợp; giá trị không hợp lệ sẽ làm lỗi ở `premain`. Cấu hình `mode` bị giới hạn vào `off` hoặc `trace`; `sample` nằm trong khoảng 0 đến 100.
5. Ví dụ chủ động từ chối khóa không được biết, mục thiếu `=`, giá trị rỗng và khóa trùng. Nó **không** hỗ trợ dấu phẩy trong giá trị, escape, quoting nội bộ, tên khóa có khoảng trắng hay cú pháp phức tạp. Nếu yêu cầu các khả năng đó, cần một parser và đặc tả options khác.
6. Đối tượng `instrumentation` do JVM cấp và được kiểm tra tồn tại. Ví dụ **chưa** đăng ký transformer nên việc in cấu hình không chứng minh class nào đã được biến đổi.

### 4.2. Tệp `Application.java`

~~~java
import java.util.Arrays;

public final class Application {
    public static void main(String[] args) {
        System.out.println("[app] main args=" + Arrays.toString(args));
    }
}
~~~

### 4.3. Tệp `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: StartupAgent

~~~

`Premain-Class` phải trỏ đúng **tên nhị phân** của lớp chứa `premain`. Vì ví dụ đặt lớp trong default package nên tên là `StartupAgent`. Nếu khai báo `package com.example.agent;`, giá trị manifest phải là `com.example.agent.StartupAgent` và JAR phải chứa đúng đường dẫn class tương ứng.

Khi tự tạo manifest, cần có newline ở cuối các dòng và kết thúc phần main manifest đúng chuẩn (thường để **một dòng trống** ở cuối như khối trên). Dùng `jar --manifest` giúp đóng gói nội dung manifest vào `META-INF/MANIFEST.MF` của JAR.

Không cần `Main-Class` trong JAR agent khi khởi động theo cách này; `Premain-Class` mới là khóa bắt buộc. `Agent-Class` phục vụ cơ chế nạp agent vào JVM đang chạy và không thay thế `Premain-Class` cho `-javaagent`.

### 4.4. Biên dịch, đóng gói, chạy

Chạy các lệnh sau trong thư mục chứa đúng ba file trên với **JDK 17 trở lên**:

~~~bash
javac StartupAgent.java Application.java
jar --create --file agent-demo.jar --manifest MANIFEST.MF StartupAgent.class
java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue
~~~

Hai lệnh đầu tạo `StartupAgent.class`, `Application.class` và `agent-demo.jar`. Lệnh `jar` ở đây chỉ đóng gói class của agent, còn `Application.class` được tìm trên `-cp .`. Dấu `.` là thư mục hiện tại. Với PowerShell trên Windows, dấu `.` trong classpath cũng hợp lệ; ví dụ này không phụ thuộc cú pháp tạo thư mục của một shell cụ thể.

**Standard output chính xác** của lệnh `java` cuối:

~~~text
[agent] raw=mode=trace,sample=25
[agent] mode=trace, sample=25, instrumentation=true
[app] main args=[red, blue]
~~~

Có thể thấy `[agent]` xuất hiện trước `[app]`; chuỗi `mode=trace,sample=25` đi vào `premain`, còn `red` và `blue` đi vào `main`. Ví dụ đã được chạy đối chiếu trên OpenJDK 21; mã và công cụ dùng API có sẵn từ Java 17.

## 5. Các biến thể nên tự chạy để hiểu `agentArgs`

### 5.1. Không truyền options

~~~bash
java -javaagent:agent-demo.jar -cp . Application
~~~

Khi chạy bằng OpenJDK 21, `raw=null` và parser dùng mặc định `mode=off, sample=10`. Phần `main` vẫn chạy với mảng đối số rỗng. Bài học quan trọng là xử lý `null` trước khi gọi `split` hoặc phương thức String khác.

### 5.2. Truyền chuỗi options rỗng

~~~bash
java -javaagent:agent-demo.jar= -cp . Application
~~~

Trên OpenJDK 21, chuỗi raw ở tình huống này là `""`: lệnh in `[agent] raw=` không có ký tự sau dấu `=`. Parser vẫn dùng cùng defaults. Điều này khác nhau ở giá trị raw so với ví dụ 5.1, nhưng không khác nhau trong cấu hình hiệu lực của demo.

### 5.3. Chỉ truyền một khóa

~~~bash
java -javaagent:agent-demo.jar=mode=trace -cp . Application
~~~

Parser đặt `mode=trace` và giữ `sample=10`. Thay đổi này đến từ `getOrDefault` trong agent, không phải cách JVM suy luận thiếu cấu hình.

### 5.4. Giá trị sai hoặc khóa trùng

~~~bash
java -javaagent:agent-demo.jar=sample=abc -cp . Application
java -javaagent:agent-demo.jar=mode=trace,mode=off -cp . Application
java -javaagent:agent-demo.jar=unknown=1 -cp . Application
~~~

Trong ví dụ, lần lượt xảy ra lỗi ép kiểu số, lỗi trùng khóa và lỗi khóa không được hỗ trợ khi chạy `premain`. Các lệnh trên dùng để **thử đường lỗi**, không phải ví dụ chạy thành công. JVM có thể in stack trace và thông báo nội bộ khác nhau theo JDK; điểm cần xác nhận là ứng dụng không được khởi động qua `main` sau một lỗi startup agent không được xử lý.

Khi xây dựng agent sản xuất, phải quyết định rõ **fail fast** hay **degrade safely**: cấu hình mâu thuẫn nghiêm trọng có thể cần chặn startup, nhưng sự cố của exporter quan sát đôi khi nên cho ứng dụng tiếp tục tùy hợp đồng hệ thống. Quyết định này thuộc thiết kế agent và yêu cầu vận hành, không thể suy từ riêng cú pháp `-javaagent`.

### 5.5. Nhiều startup agents

Một JVM hỗ trợ tùy chọn `-javaagent` có thể nhận nhiều lần khai báo:

~~~bash
java -javaagent:first-agent.jar=level=basic -javaagent:second-agent.jar=enabled=true -cp . Application
~~~

Đây là minh họa cú pháp; hai file JAR phải có thật và hợp lệ. JVM gọi các `premain` theo **thứ tự khai báo** trước khi gọi `Application.main`. Mỗi agent nhận **phần options đi kèm chính JAR của mình**. Một đường dẫn agent JAR cũng có thể được dùng nhiều lần, nhưng cần cân nhắc tác dụng phụ nếu initialization không idempotent.

## 6. Quoting, khoảng trắng và cấu hình có ký tự đặc biệt

Có hai cấp xử lý khác nhau:

1. **Shell/terminal** phân tách lệnh thành các argument cho `java` và xử lý dấu nháy, biến môi trường, ký tự điều khiển.
2. **Java launcher** nhận một argument `-javaagent:...`, tìm agent JAR và tách ra options để truyền tới `premain`.

Nếu đường dẫn JAR chứa khoảng trắng, đặt **toàn bộ đối số JVM** trong dấu nháy theo quy tắc của shell đang dùng. Ví dụ minh họa với một file thực sự nằm ở thư mục `my agents`:

~~~bash
java "-javaagent:my agents/agent-demo.jar=mode=trace,sample=25" -cp . Application
~~~

Dấu nháy ở đây giúp shell gửi một argument tới `java`; dấu nháy không trở thành nội dung của `agentArgs`. Cách xử lý các ký tự như `&`, `;`, `|`, dấu nháy lồng nhau và ký hiệu biến môi trường phụ thuộc shell (bash, PowerShell, cmd.exe). Không viết hướng dẫn cấu hình bằng cách sao chép tùy tiện cú pháp escape của một shell sang shell khác.

Tương tự, giả sử options có giá trị dài:

~~~text
mode=trace,endpoint=https://collector.example.test/v1/trace
~~~

JVM chỉ chuyển **nguyên chuỗi** đó; chính parser agent phải biết `endpoint` là gì. Parser demo ở phần 4 **cố ý không hỗ trợ** `endpoint` nên sẽ từ chối ví dụ này. Khi options có dấu phẩy trong giá trị, không thể dùng `split(",")` đơn giản mà vẫn bảo toàn dữ liệu. Cần thiết kế cơ chế escape/encode rõ ràng (hoặc truyền đường dẫn đến một file cấu hình riêng), rồi kiểm thử các giá trị có dấu đặc biệt.

Một nguyên tắc thực hành: **đừng ghi secret/token vào options nếu có thể tránh**, vì lệnh khởi chạy và tham số process có thể được lưu trong script, hệ thống triển khai, công cụ giám sát hoặc nhật ký vận hành. Ưu tiên cấu hình an toàn thích hợp với môi trường, tránh vô tình in toàn bộ `agentArgs` chứa bí mật. Demo cố ý in raw để phục vụ học tập, không nên dùng cách log đó nguyên trạng trong production.

## 7. Từ `agentArgs` tới cấu hình agent thực tế

Một agent có thể dùng `agentArgs` để quyết định:

- **Bật/tắt chức năng:** `mode=off`, `mode=trace`, mức ghi log hoặc tập lớp cần instrument.
- **Mức thu thập:** tỉ lệ sampling, giới hạn số sự kiện, kích thước buffer.
- **Đích xuất dữ liệu:** tên endpoint, service name, timeout, batch settings.
- **Điều kiện áp dụng:** package prefixes, tên lớp, rule include/exclude, phiên bản cấu hình.

Những khóa này chỉ là **ví dụ về lựa chọn của tác giả agent**. Java không tiêu chuẩn hóa `mode`, `sample`, `endpoint` hay định dạng phân cách `,`. Khi dùng agent của bên thứ ba, phải đọc đúng tài liệu của agent đó; phần options hợp lệ của một agent có thể hoàn toàn khác agent khác.

Một quy trình khởi tạo tốt thường theo thứ tự:

1. Nhận nguyên `agentArgs`, kiểm tra null/empty và chọn default có tài liệu.
2. Parse theo **grammar của agent** và báo lỗi rõ ràng với khóa, kiểu hoặc giá trị sai.
3. Xác nhận cấu hình nhất quán, không chứa dữ liệu nhạy cảm trong log.
4. Khởi tạo tài nguyên có giới hạn, chỉ sau khi cấu hình hợp lệ mới đăng ký hook/transformer.
5. Trả khỏi `premain` để ứng dụng tiếp tục vào `main`; nếu có lỗi không thể khôi phục, đưa ra thông báo khởi động hữu ích.

Đừng khởi động network exporter hoặc bắt đầu một tác vụ dài rồi đợi vô hạn ngay trong `premain`. Vì ứng dụng chờ agent khởi tạo xong, việc block ở đó có thể khiến dịch vụ chưa bao giờ đạt trạng thái sẵn sàng.

## 8. Lỗi phổ biến và cách xác minh

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| JVM báo không mở được agent JAR | `jarpath` sai, file chưa tạo, không có quyền đọc | Kiểm tra đường dẫn tính từ thư mục đang chạy, tên file và quyền truy cập |
| Không tìm thấy `Premain-Class` | Manifest thiếu hoặc đóng gói sai | Kiểm tra `META-INF/MANIFEST.MF` trong agent JAR và giá trị tên lớp |
| Không nạp được agent class | Tên nhị phân, đường dẫn class hoặc dependency sai | Kiểm tra các entry của JAR và classpath/dependency của agent |
| `premain` không được gọi | Sai chữ ký `public static void`, thiếu manifest, hoặc đặt `-javaagent` sai vị trí | Xem lỗi khởi động và thử demo tối giản trước |
| `agentArgs` bất ngờ rỗng/null | Không có `=options` hoặc vô tình chỉ truyền dấu `=` | In raw có kiểm soát ở môi trường thử, kiểm tra CLI |
| `agentArgs` khác ý định | Shell tách theo khoảng trắng hoặc xử lý ký tự đặc biệt | Quote đúng cả đối số và xem lệnh process thực nhận |
| Parser lỗi với dấu phẩy hoặc dấu `=` | Grammar parser tự viết quá đơn giản | Thêm test cho escaping, ký tự phân cách và giá trị rỗng |
| `main(args)` nhận `-javaagent` như text | Tùy chọn được đặt sau tên lớp chính hoặc sau `-jar app.jar` | Đưa `-javaagent` lên trước phần chọn lớp/JAR ứng dụng |
| App không bắt đầu khi options sai | `premain` ném ngoại lệ không được xử lý | Sửa cấu hình hoặc chính sách lỗi startup của agent |
| Agent chạy nhưng thiếu dữ liệu đo | Chưa đăng ký transformer, class đã load hoặc thiếu coverage | Kiểm tra hook thực tế, class loading và API instrumentation |

Kiểm tra đóng gói bằng công cụ JDK:

~~~bash
jar --list --file agent-demo.jar
~~~

Trong danh sách phải có `META-INF/MANIFEST.MF` và `StartupAgent.class`. Để đọc nội dung manifest, dùng công cụ xem JAR/ZIP của môi trường hoặc giải nén vào **thư mục thử nghiệm riêng**, rồi kiểm tra chính xác `Premain-Class`. Không cần có `Main-Class` trong agent JAR của ví dụ.

**Checklist trước khi dùng trong hệ thống thực:**

- `-javaagent` xuất hiện đúng vị trí trong lệnh khởi chạy của **tiến trình cần instrument**, không chỉ trong lệnh build.
- Agent JAR có `Premain-Class` hợp lệ và đầy đủ dependency mà agent cần.
- Cấu hình được parse và validate; có chính sách rõ cho khi không truyền options, chuỗi rỗng và lỗi cấu hình.
- Log cấu hình tránh secret, không tự làm app treo hoặc ghi đè lỗi nghiệp vụ.
- Nếu có nhiều agent, kiểm tra thứ tự chạy, xung đột hook và quá trình khởi tạo.
- Đã thử với JDK, shell và cách đóng gói thực tế; nhận biết giới hạn class loading và coverage.

## 9. Tự kiểm tra kiến thức

1. Với lệnh `java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue`, chuỗi đi vào `premain` là gì? Mảng đi vào `main` là gì?
2. Ai quyết định ý nghĩa của dấu phẩy và hai khóa `mode`, `sample`: JVM hay agent?
3. Vì sao `Premain-Class` khác `Main-Class`? Khi nào cần `Agent-Class`?
4. Tại sao phải xử lý cả `null` và `""` trước khi gọi `split`?
5. Nếu agent khai báo cả hai biến thể `premain`, JVM ưu tiên biến thể nào?
6. Khi một agent startup ném ngoại lệ trong `premain`, ứng dụng đã chạy đến `main` hay chưa?
7. Tại sao cách viết `-javaagent` sau `Application` làm thay đổi ý nghĩa của nó?
8. Bạn sẽ thiết kế parser ra sao nếu giá trị chứa dấu phẩy, khoảng trắng hoặc ký tự cần escape?

## 10. Tóm tắt để áp dụng

`-javaagent:jarpath[=options]` là **đầu vào của JVM launcher để kích hoạt một startup agent**. Manifest `Premain-Class` xác định lớp khởi động; JVM gọi `premain` trước `main`; `options` đi vào một tham số `String agentArgs` nguyên vẹn. Java **không** phân tích các key/value tùy chỉnh thay cho agent. Do đó, cách dùng đúng gồm ba việc: viết lệnh khởi chạy đúng vị trí, đóng gói đúng manifest và xây parser/validation đủ rõ cho chuỗi agentArgs.

### Tham khảo chính thức

- [Oracle Java 17 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, cú pháp `-javaagent`, chữ ký `premain`, manifest, agent options và thứ tự nhiều agent.
- [Oracle Java 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): đặc tả tương ứng trên JDK 21, giới hạn và khả năng của agent.
- [Oracle Java 17 — Class Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): vai trò của đối tượng `Instrumentation` do JVM truyền vào `premain`.