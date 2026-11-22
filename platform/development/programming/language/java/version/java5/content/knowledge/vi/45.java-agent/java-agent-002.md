# Cấu trúc agent JAR và thuộc tính Premain-Class

Một Java agent là mã được JVM gọi để chuẩn bị công cụ theo dõi hoặc can thiệp vào quá trình nạp lớp. Hãy hình dung ứng dụng có cửa vào `main`, còn agent khởi động cùng JVM có cửa vào `premain`. Bài này tập trung vào việc đóng gói và nối đúng cửa vào đó; chưa cần biến đổi bytecode.

## 1. Ba phần phải khớp nhau

Với ví dụ trong bài, cần nối đúng ba thông tin:

```text
-javaagent:dist/startup-agent.jar
                 |
                 v
META-INF/MANIFEST.MF
Premain-Class: demo.agent.StartupAgent
                 |
                 v
demo/agent/StartupAgent.class
public static void premain(...)
```

Tên tệp JAR có thể do bạn chọn. Tên lớp trong manifest phải khớp với lớp thực tế. Chẳng hạn, đổi tên JAR thành `monitor.jar` chỉ làm thay đổi đường dẫn trong lệnh chạy; đổi package của lớp lại đòi hỏi cập nhật `Premain-Class`.

JVM đọc thuộc tính trong **phần chính** của manifest để chọn lớp agent, rồi gọi `premain` trước `main` của ứng dụng. Nó ưu tiên chữ ký hai tham số; nếu không có, mới tìm chữ ký một tham số:

```java
public static void premain(String agentArgs, Instrumentation inst)
public static void premain(String agentArgs)
```

Đây là hai lựa chọn chữ ký, không phải hai phương thức bắt buộc cùng tồn tại. Đối tượng `Instrumentation` do JVM truyền vào. Tham số `agentArgs` nhận một chuỗi tùy chọn; agent tự quyết định cách phân tích chuỗi đó. Xem [hợp đồng khởi động Java agent](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html).

## 2. Cấu trúc bên trong JAR

Ví dụ tối thiểu sẽ tạo:

```text
startup-agent.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    └── agent/
        └── StartupAgent.class
```

Phân biệt ba cách biểu diễn:

| Vị trí | Giá trị trong ví dụ |
| --- | --- |
| Mã nguồn Java | `package demo.agent;` |
| Manifest | `demo.agent.StartupAgent` |
| Đường dẫn bên trong JAR | `demo/agent/StartupAgent.class` |

Không ghi `demo/agent/StartupAgent.class` vào `Premain-Class`. Đó là đường dẫn mục trong ZIP, không phải tên nhị phân của lớp.

Tệp manifest nguồn, đặt tên `agent.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent

```

`Manifest-Version` là phiên bản định dạng manifest, không phải phiên bản Java hay phiên bản agent. Mỗi thuộc tính có dạng `Tên: giá-trị`; có dấu cách sau dấu hai chấm. Kết thúc tệp bằng ký tự xuống dòng; ví dụ trên có thêm dòng trống kết thúc phần chính. Không chuyển `Premain-Class` xuống một phần riêng bắt đầu bằng `Name:`.

Manifest thực tế nằm tại `META-INF/MANIFEST.MF`; tệp `agent.mf` bên ngoài chỉ là đầu vào cho công cụ đóng gói. Công cụ có thể bổ sung `Created-By`, nên manifest sau đóng gói có thể có thêm thông tin. Xem [đặc tả JAR và manifest](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html).

## 3. Ví dụ hoàn chỉnh chạy bằng JDK 17+

Ví dụ cố ý chỉ in thông tin để quan sát thứ tự chạy. Một agent chưa đăng ký bộ biến đổi lớp vẫn là agent hợp lệ.

Tạo thư mục làm việc riêng:

```text
agent-demo/
├── agent.mf
└── src/
    └── demo/
        ├── agent/
        │   └── StartupAgent.java
        └── app/
            └── Main.java
```

### 3.1. Lớp agent

Tệp `src/demo/agent/StartupAgent.java`:

```java
package demo.agent;

import java.lang.instrument.Instrumentation;

public class StartupAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("agent.options=" + agentArgs);
        System.out.println("agent.instrumentation=" + (inst != null));
    }
}
```

Không tự tạo một lớp triển khai `Instrumentation` để thay thế đối tượng JVM cung cấp. Trong ví dụ, phép kiểm tra khác `null` chỉ giúp nhìn thấy tham số đã được truyền. API này còn cung cấp các thao tác đăng ký bộ biến đổi lớp và truy vấn khả năng của JVM; chúng là bước tiếp theo sau khi đóng gói đúng. Xem [API Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).

### 3.2. Ứng dụng được chạy cùng agent

Tệp `src/demo/app/Main.java`:

```java
package demo.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("app.main");
        System.out.println("app.argument=" + args[0]);
    }
}
```

Chương trình này yêu cầu một đối số ứng dụng. Các lệnh dưới đây luôn truyền `hello`; nếu bỏ nó, dòng truy cập `args[0]` sẽ gây lỗi. Đây là điều kiện của chương trình mẫu, không phải yêu cầu của agent.

### 3.3. Biên dịch và đóng gói

Mở PowerShell tại `agent-demo`. Cần JDK có `java`, `javac` và `jar` trong `PATH`. Lưu các tệp Java bằng UTF-8 không BOM.

```powershell
New-Item -ItemType Directory -Force out/agent, out/app, dist | Out-Null
javac --release 17 -d out/agent src/demo/agent/StartupAgent.java
javac --release 17 -d out/app src/demo/app/Main.java
jar --create --file dist/startup-agent.jar --manifest agent.mf -C out/agent .
```

`--release 17` tạo class file phù hợp Java 17. Chỉ tiếp tục khi từng lệnh thành công.

Trong lệnh đóng gói, `--manifest` đưa nội dung `agent.mf` vào manifest của JAR. `-C out/agent .` lấy nội dung bên trong thư mục lớp đã biên dịch, nhờ vậy đường dẫn mục bắt đầu bằng `demo/`, không phải `out/agent/demo/`. Xem [công cụ jar](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html).

Kiểm tra sản phẩm:

```powershell
jar --list --file dist/startup-agent.jar
```

Với các tệp ví dụ, danh sách là:

```text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/agent/
demo/agent/StartupAgent.class
```

Ứng dụng nằm riêng trong `out/app`. Nó không bị đóng gói nhầm vào JAR của agent.

### 3.4. Chạy và đọc kết quả

```powershell
java '-javaagent:dist/startup-agent.jar=mode=demo' -cp out/app demo.app.Main hello
```

Stdout:

```text
agent.options=mode=demo
agent.instrumentation=true
app.main
app.argument=hello
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm chứng trên OpenJDK 24.0.2.

Quan sát trực tiếp:

- Hai dòng của agent xuất hiện trước `app.main`.
- Chuỗi `mode=demo` đi vào `agentArgs`.
- `hello` đi vào mảng `args` của ứng dụng.
- Không cần thêm JAR agent vào `-cp` trong ví dụ này.

Dấu bằng đầu tiên sau tên JAR phân cách đường dẫn với tùy chọn agent; dấu bằng trong `mode=demo` thuộc nội dung tùy chọn. JVM không tự biến chuỗi đó thành một bản đồ cấu hình.

Đặt tùy chọn JVM trước tên lớp ứng dụng. Nếu viết:

```powershell
java -cp out/app demo.app.Main hello '-javaagent:dist/startup-agent.jar=mode=demo'
```

thì `-javaagent:...` ở vị trí đối số ứng dụng. Với chương trình mẫu, stdout chỉ có:

```text
app.main
app.argument=hello
```

Lệnh đúng và lệnh sai vị trí cho thấy cùng một chuỗi ký tự có thể có vai trò khác nhau tùy vị trí trên dòng lệnh.

## 4. Phân biệt các thuộc tính chọn điểm vào

| Thuộc tính | Trường hợp |
| --- | --- |
| `Premain-Class` | Agent được chỉ định bằng `-javaagent`; gọi `premain` |
| `Main-Class` | Điểm vào ứng dụng khi chạy `java -jar` |
| `Agent-Class` | Điểm vào `agentmain` cho cơ chế nạp agent vào JVM đang chạy |
| `Launcher-Agent-Class` | Agent được đóng gói cùng ứng dụng executable JAR; dùng `agentmain` trước `main` |

Bảng dùng để phân biệt vai trò manifest. Bài thực hành chỉ dùng đường khởi động `-javaagent`. Không cần thêm tất cả thuộc tính vào JAR tối thiểu. Đặc biệt, thêm `Main-Class` không thay cho `Premain-Class`. Hợp đồng các điểm vào được mô tả trong [java.lang.instrument](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html) và [đặc tả executable JAR](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html).

Các thuộc tính `Can-Redefine-Classes` và `Can-Retransform-Classes` khai báo khả năng agent cần dùng; mặc định là `false`. Chỉ khai báo khi thiết kế agent cần đến. Việc ghi `true` không làm mọi lớp tự động biến đổi được: mã agent cần kiểm tra khả năng JVM và điều kiện của từng thao tác qua [Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).

## 5. Đọc lỗi theo chuỗi đóng gói

Thay vì sửa nhiều thứ cùng lúc, kiểm tra từ JAR đến manifest, lớp rồi chữ ký:

| Hiện tượng | Việc kiểm tra đầu tiên |
| --- | --- |
| Không mở được JAR | Đường dẫn `dist/startup-agent.jar` tính từ thư mục hiện tại |
| Không tìm thấy `Premain-Class` | Manifest thực sự trong JAR; thuộc tính nằm ở phần chính |
| Không nạp được lớp agent | Package, chữ hoa/thường và mục `demo/agent/StartupAgent.class` |
| Không tìm được `premain` phù hợp | Tên phương thức, `public static`, kiểu trả về `void`, kiểu tham số |
| Không tìm thấy lớp phụ trợ | Những lớp mà agent thực sự phụ thuộc đã được phân phối và nạp được chưa |
| Không thấy dòng in của agent | Vị trí `-javaagent` và có đang chạy đúng JAR vừa tạo không |

Nếu đóng gói thêm lớp phụ trợ, hãy kiểm tra chúng bằng `jar --list` như kiểm tra `StartupAgent.class`. Chỉ đổi đuôi một ZIP thành `.jar`, hoặc chỉ đặt tệp mã nguồn `.java` vào JAR, chưa tạo ra sản phẩm tương đương ví dụ đã biên dịch.

Lỗi khởi động agent như không nạp được lớp, thiếu phương thức phù hợp hoặc ngoại lệ không được xử lý trong `premain` có thể khiến JVM dừng trước `main`; xem [quy tắc lỗi khi khởi động agent](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html). Vì vậy, thử JAR agent với một ứng dụng nhỏ trước giúp tách lỗi đóng gói khỏi lỗi của ứng dụng lớn.

## 6. Tự kiểm tra

1. Đổi tên `startup-agent.jar` nhưng giữ nguyên lớp agent: cần sửa đường dẫn nào trong lệnh chạy?
2. Chuyển `StartupAgent` sang package `demo.monitor`: manifest và đường dẫn mục trong JAR phải đổi thế nào?
3. Vì sao `Main-Class: demo.agent.StartupAgent` chưa đủ cho lệnh `-javaagent`?
4. Trong lệnh chạy đúng, chuỗi nào thuộc agent và chuỗi nào thuộc ứng dụng?
5. Nếu muốn agent nhận `mode=test`, có cần biên dịch lại không?

Có thể trả lời bằng sản phẩm đã tạo: tên JAR nối tới manifest, manifest nối tới tên lớp, và lớp cung cấp đúng `premain`. Khi ba phần này khớp, việc thử nghiệm chức năng agent mới có nền tảng đáng tin cậy.
