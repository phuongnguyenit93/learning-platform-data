# premain và khởi chạy bằng -javaagent

## 1. Điểm vào trước main của ứng dụng

Java agent là mã được JVM nạp để hỗ trợ các công cụ như theo dõi hiệu năng, thu thập dấu vết hoặc đo độ bao phủ kiểm thử. Khi được khai báo bằng `-javaagent` lúc khởi động, agent có điểm vào tên `premain`. JVM gọi điểm vào này trước `main` của ứng dụng, tạo cơ hội thiết lập công cụ trước khi ứng dụng bắt đầu thực thi.

Cơ chế này vẫn được Java hiện đại hỗ trợ; ví dụ bên dưới dùng mã và công cụ Java 17+, không yêu cầu chạy JDK 5. Cần phân biệt ba thành phần:

- **Agent JAR**: chứa lớp agent và manifest chỉ ra điểm vào.
- **`premain`**: phương thức JVM gọi khi kích hoạt agent bằng `-javaagent`.
- **`Instrumentation`**: đối tượng JVM cấp cho agent để đăng ký công cụ biến đổi bytecode và thực hiện các thao tác được API cho phép.

Có `premain` chưa đồng nghĩa lớp ứng dụng đã được biến đổi. Agent phải chủ động đăng ký bộ biến đổi hoặc gọi API phù hợp. Bài này tập trung khởi động agent, chưa thực hiện biến đổi bytecode. Xem [API Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).

## 2. Hợp đồng của premain

Có hai chữ ký hợp lệ:

```java
public static void premain(String agentArgs, Instrumentation inst)
public static void premain(String agentArgs)
```

Đây là khai báo chữ ký để đối chiếu, không phải chương trình độc lập. Với dạng hai tham số, cần nhập `java.lang.instrument.Instrumentation`.

JVM tìm dạng hai tham số trước; nếu không có thì tìm dạng một tham số. Nếu lớp có cả hai, JVM chọn dạng hai tham số, không gọi lần lượt cả hai. Nên dùng dạng hai tham số khi cần API instrumentation; không tự tạo đối tượng `Instrumentation`.

`premain` phải là `public static` và trả về `void`. Nó không cần triển khai một interface hay kế thừa lớp agent đặc biệt. Gọi `premain(...)` bằng mã Java thông thường cũng không thay thế việc JVM kích hoạt agent.

Luồng khởi động có thể hình dung:

```text
java -javaagent:agent.jar ... demo.app.Main
  -> JVM khởi tạo
  -> nạp lớp agent theo Premain-Class
  -> gọi premain và đợi phương thức trả về
  -> gọi main của ứng dụng
```

“Trước main” không có nghĩa “trước mọi lớp của JVM”: nhiều lớp nền tảng và lớp mà agent sử dụng đã được nạp trong quá trình khởi động. `premain` cần hoàn tất phần khởi tạo đồng bộ trước khi trả về; nếu tự tạo luồng nền, JVM không đợi luồng đó hoàn thành mới vào `main`. Hợp đồng này được mô tả trong [đặc tả java.lang.instrument của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).

## 3. Manifest nối JAR với lớp agent

Trong phần chính của `META-INF/MANIFEST.MF` cần có:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent

```

`demo.agent.StartupAgent` là tên nhị phân của lớp, phân biệt chữ hoa/thường; không viết đường dẫn `demo/agent/StartupAgent.class` ở thuộc tính này.

Tệp manifest dùng để đóng gói phải kết thúc bằng ký tự xuống dòng. Trong ví dụ, để một dòng trống sau các thuộc tính giúp kết thúc phần chính rõ ràng; lưu văn bản không có BOM. Cú pháp và cách kết thúc phần manifest theo [đặc tả JAR](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html).

Không đánh đồng các thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| `Premain-Class` | Lớp agent được chọn khi chạy bằng `-javaagent` |
| `Main-Class` | Điểm vào ứng dụng khi chạy bằng `java -jar` |
| `Agent-Class` | Lớp dùng cho cơ chế nạp agent vào JVM đang chạy |

Chỉ có `Main-Class` hoặc `Agent-Class` không đáp ứng yêu cầu của `-javaagent`. Một agent JAR phục vụ cách chạy trong bài không cần `Main-Class`.

Các thuộc tính `Can-Redefine-Classes` và `Can-Retransform-Classes` cũng không bắt buộc cho ví dụ khởi động này. Không khai báo hàng loạt khả năng chỉ vì đang xây dựng agent; cần gì thì khai báo và kiểm tra hỗ trợ của JVM theo API tương ứng.

## 4. Cú pháp dòng lệnh và hai luồng tham số

Cú pháp:

```text
-javaagent:<đường-dẫn-agent.jar>[=<chuỗi-tùy-chọn>]
```

Ví dụ:

```shell
java "-javaagent:agent.jar=mode=trace,label=demo" -cp out/app demo.app.Main hello
```

Có hai luồng tham số riêng:

- `premain` nhận chuỗi `mode=trace,label=demo`.
- `main(String[] args)` nhận mảng có một phần tử `hello`.

JVM chuyển chuỗi tùy chọn của agent thành **một chuỗi**, không tự hiểu dấu phẩy hay tự tạo bản đồ khóa–giá trị. Nếu agent muốn cú pháp `mode=trace,label=demo`, chính agent phải phân tích và kiểm tra nó. Không giả định mọi thư viện agent chấp nhận cùng định dạng.

Đặt tùy chọn JVM trước tên lớp chính, hoặc trước `-jar`:

```shell
java "-javaagent:agent.jar=mode=trace" -jar application.jar hello
```

Trong lệnh trên, `application.jar` phải là JAR ứng dụng có cấu hình điểm vào phù hợp. Đây là mẫu lệnh để áp dụng cho ứng dụng của bạn, chưa phải JAR được tạo trong ví dụ tiếp theo.

Nếu đặt `-javaagent:...` sau tên lớp chính hoặc sau tên JAR ứng dụng, nó trở thành tham số của `main`, không bật agent. Quy tắc vị trí tham số xem [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Đường dẫn agent tương đối được giải theo thư mục làm việc của tiến trình. Nếu có khoảng trắng, đặt toàn bộ đối số trong dấu ngoặc kép:

```shell
java "-javaagent:tools/My Agent.jar=mode=trace" -cp out/app demo.app.Main
```

Không để lệnh triển khai phụ thuộc ngầm vào thư mục làm việc khác với khi thử nghiệm.

## 5. Ví dụ hoàn chỉnh: chứng minh premain chạy trước main

Tạo ba tệp dưới cùng một thư mục làm việc:

```text
src/
  agent/demo/agent/StartupAgent.java
  app/demo/app/Main.java
agent-manifest.mf
```

### Lớp agent

Tệp `src/agent/demo/agent/StartupAgent.java`:

```java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("agent: " + agentArgs);
        System.setProperty("demo.agent.ready", "true");
    }
}
```

Agent in chuỗi tùy chọn rồi đặt một thuộc tính hệ thống dùng chung trong JVM. Ví dụ cố ý không dùng `inst` để giữ phép kiểm chứng tập trung vào thời điểm khởi động. Trong công cụ thực tế, đây có thể là nơi đăng ký bộ biến đổi lớp.

### Lớp ứng dụng

Tệp `src/app/demo/app/Main.java`:

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(
                "main: ready=" + System.getProperty("demo.agent.ready", "false"));
        System.out.println("main args: " + String.join(",", args));
    }
}
```

Ứng dụng không nhập lớp agent, không gọi `premain` và không phụ thuộc agent khi biên dịch. Giá trị mặc định `false` giúp so sánh hai cách khởi chạy.

### Manifest và đóng gói

Nội dung tệp `agent-manifest.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent

```

Từ thư mục chứa `src` và manifest, dùng JDK 17 trở lên:

```shell
javac --release 17 -d out/agent src/agent/demo/agent/StartupAgent.java
javac --release 17 -d out/app src/app/demo/app/Main.java
jar --create --file agent.jar --manifest agent-manifest.mf -C out/agent .
java "-javaagent:agent.jar=mode=trace,label=demo" -cp out/app demo.app.Main hello
```

`-d` chỉ định thư mục đầu ra của lớp đã biên dịch. `-C out/agent .` đóng gói nội dung bên trong thư mục đó vào gốc JAR, nên lớp có đường dẫn đúng `demo/agent/StartupAgent.class`. Cú pháp đóng gói xem [tài liệu lệnh jar](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html).

Stdout của lệnh chạy:

```text
agent: mode=trace,label=demo
main: ready=true
main args: hello
```

Ba dòng chứng minh:

1. Agent được kích hoạt bằng tùy chọn JVM.
2. Thuộc tính do `premain` đặt đã có khi `main` đọc.
3. Tùy chọn agent không bị trộn vào tham số ứng dụng.

Chạy lại cùng ứng dụng nhưng không bật agent:

```shell
java -cp out/app demo.app.Main hello
```

Stdout:

```text
main: ready=false
main args: hello
```

Mỗi lệnh `java` tạo một JVM mới; thuộc tính được đặt ở lần chạy trước không tồn tại sang lần chạy này.

Có thể kiểm tra cấu trúc JAR:

```shell
jar --list --file agent.jar
```

Danh sách phải có `META-INF/MANIFEST.MF` và `demo/agent/StartupAgent.class`. Thứ tự và các mục thư mục trong danh sách có thể khác; không dùng chúng làm bằng chứng về thứ tự thực thi.

## 6. Nhiều agent và tác động đến khởi động

Có thể khai báo nhiều lần `-javaagent`:

```shell
java "-javaagent:agent.jar=first" "-javaagent:agent.jar=second" -cp out/app demo.app.Main hello
```

Với agent của ví dụ, stdout là:

```text
agent: first
agent: second
main: ready=true
main args: hello
```

JVM gọi các `premain` theo thứ tự agent được liệt kê. Cùng một JAR cũng có thể xuất hiện nhiều lần. Tuy vậy, không suy rộng thứ tự gọi `premain` thành một quy tắc đơn giản cho mọi hoạt động biến đổi bytecode; thứ tự gọi các bộ biến đổi còn có hợp đồng riêng.

Nếu agent không nạp được, không có chữ ký `premain` hợp lệ, hoặc `premain` ném ngoại lệ/lỗi không được xử lý, JVM hủy khởi động trước khi gọi `main`. Do đó, agent là một phần của đường khởi động quan trọng. Hợp đồng hiện hành được mô tả trong [đặc tả khởi động agent Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html#starting-an-agent-from-the-command-line-interface).

Trong `premain`, nên xác thực cấu hình sớm, khởi tạo gọn và tránh chờ mạng vô hạn. Nếu thiết kế công cụ cho phép ứng dụng tiếp tục khi một chức năng phụ lỗi, cần xử lý ngoại lệ có chủ đích và báo rõ chức năng nào bị tắt; không âm thầm nuốt mọi lỗi.

Agent chạy cùng tiến trình và có khả năng tác động sâu đến ứng dụng. Chỉ dùng JAR đã kiểm chứng nguồn gốc; không đưa mật khẩu hoặc token vào tùy chọn dòng lệnh vì cấu hình khởi chạy có thể bị ghi log hoặc hiển thị qua công cụ quản trị tiến trình.

## 7. Chẩn đoán lỗi thường gặp

| Hiện tượng | Kiểm tra |
| --- | --- |
| JVM báo không đọc được agent JAR hoặc manifest | Đường dẫn, quyền đọc, tệp có thực sự là JAR hợp lệ không |
| Báo thiếu `Premain-Class` | Đọc manifest thực sự trong JAR, không chỉ tệp nguồn trước đóng gói |
| Không tìm thấy lớp agent | Tên package/class trong manifest và đường dẫn lớp trong JAR |
| Không tìm thấy điểm vào hợp lệ | Đúng `public static void premain`, đúng kiểu và số tham số |
| `NoClassDefFoundError` trong agent | Các thư viện mà agent dùng có thực sự được cung cấp và nhìn thấy bởi bộ nạp lớp không |
| Ứng dụng chạy nhưng không có dòng `agent:` | Kiểm tra lệnh thực tế: tùy chọn có nằm trước lớp chính/`-jar` không |
| `UnsupportedClassVersionError` | Agent hoặc thư viện của nó được biên dịch cho Java mới hơn JVM đang chạy |
| Ứng dụng không vào `main` | Đọc stderr và nguyên nhân đầu tiên từ khởi tạo agent; kiểm tra chờ vô hạn trong `premain` |

Không chép nguyên văn một thông báo lỗi JVM làm hợp đồng ổn định giữa mọi JDK; xác định nguyên nhân dựa trên manifest, lớp, chữ ký và lệnh thực tế.

Cuối cùng, `-javaagent` là cách khai báo agent ngay khi khởi động. Nó khác cơ chế nạp agent vào một JVM đang chạy qua `agentmain`. Cảnh báo hoặc thiết lập cho **nạp động** không có nghĩa phải bật thêm cờ nạp động để chạy ví dụ `-javaagent` này. Khi triển khai trên JDK khác, đối chiếu tài liệu đúng phiên bản và khả năng tương thích do nhà cung cấp agent công bố.

## 8. Tự thực hành

- Đổi chuỗi sau dấu `=` của `-javaagent`; xác nhận chỉ dòng `agent:` đổi.
- Đổi `hello` thành hai đối số `hello world`; dự đoán `main args: hello,world`.
- Đưa tùy chọn agent xuống sau `demo.app.Main`; giải thích vì sao ứng dụng nhận nó như tham số.
- Chạy với hai lần khai báo agent; xác định phần nào chứng minh thứ tự gọi `premain`.
- Bỏ `Premain-Class` trong một bản JAR thử nghiệm rồi chạy lại; quan sát ứng dụng không tới `main`.

Sau các phép thử, bạn cần tự nối được bốn mắt xích: tùy chọn JVM chọn agent JAR, manifest chọn lớp, JVM chọn chữ ký `premain`, rồi mới chuyển điều khiển sang `main` khi agent khởi tạo xong.
