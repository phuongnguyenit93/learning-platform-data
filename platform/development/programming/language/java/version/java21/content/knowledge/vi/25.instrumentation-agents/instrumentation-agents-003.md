# Khai báo -javaagent hoặc -agentlib theo hướng dẫn của công cụ

Một công cụ giám sát, profiler, coverage hoặc debugger có thể yêu cầu nạp agent khi khởi động JVM. Trước khi thêm tùy chọn vào lệnh chạy, cần xác định công cụ yêu cầu **Java agent** hay **native agent**:

- **-javaagent** nạp agent được đóng gói trong JAR và khởi chạy bằng phương thức Java **premain()**.
- **-agentlib** nạp thư viện native agent theo tên thư viện; với JVMTI, JVM gọi native entry point **Agent_OnLoad()**.
- **-agentpath** cũng nạp native agent, nhưng chỉ rõ đường dẫn tuyệt đối đến thư viện.

Ba tùy chọn không thể thay thế tùy ý cho nhau. Hãy làm theo chính xác tài liệu cài đặt của công cụ, gồm loại agent, đường dẫn, tham số và thứ tự khởi chạy.

## 1. Xác định loại agent mà công cụ yêu cầu

| Dấu hiệu trong tài liệu công cụ | Tùy chọn thường dùng | Artifact cần có |
|---|---|---|
| Agent JAR, Premain-Class, premain() | -javaagent:<jarpath>[=<options>] | JAR có manifest khai báo agent class |
| Native library, JVMTI, Agent_OnLoad | -agentlib:<libname>[=<options>] | Thư viện native tương ứng với hệ điều hành và kiến trúc |
| Đường dẫn đầy đủ đến DLL hoặc shared library | -agentpath:<pathname>[=<options>] | File thư viện native tại đường dẫn chỉ định |
| Java debugger dùng JDWP | -agentlib:jdwp=<options> | JDWP agent đi kèm JDK |

Java agent thuộc cơ chế **java.lang.instrument**. Agent nhận đối tượng **Instrumentation** để đăng ký transformer hoặc thực hiện các thao tác instrumentation được JVM hỗ trợ.

Native agent thường sử dụng **JVM Tool Interface (JVMTI)**. Đây là giao diện native dành cho công cụ cần quan sát hoặc điều khiển trạng thái JVM, chẳng hạn debugger, profiler hoặc công cụ phân tích thread.

Nếu tài liệu chỉ ghi "enable agent", hãy kiểm tra phần cài đặt của công cụ để biết artifact và loại agent. Không suy luận loại agent từ tên file hoặc đổi -javaagent thành -agentlib khi lệnh ban đầu không chạy.

## 2. Khai báo Java agent bằng -javaagent

Cú pháp của launcher Java 21:

~~~text
-javaagent:<jarpath>[=<options>]
~~~

- **jarpath** là đường dẫn tới agent JAR.
- **options** là chuỗi tùy chọn riêng của agent, được truyền vào phương thức premain().
- Phần =<options> có thể bỏ qua nếu agent không cần tham số.

Ví dụ chạy ứng dụng JAR với một agent:

~~~bash
java -javaagent:tools/metrics-agent.jar=env=prod,interval=10 -jar application.jar
~~~

Tùy chọn agent phải nằm trong nhóm tùy chọn của JVM, trước tên main class hoặc trước -jar application.jar. Trong ví dụ, JVM nạp metrics-agent trước khi gọi main của ứng dụng.

Không đặt -javaagent sau tên JAR ứng dụng. Khi đó, phần nằm sau -jar application.jar được truyền cho main(String[] args) dưới dạng đối số ứng dụng, không còn là tùy chọn khởi động agent.

## 3. Agent JAR phải khai báo Premain-Class

Agent JAR khởi chạy bằng -javaagent phải có thuộc tính **Premain-Class** trong phần main của manifest. Giá trị là tên nhị phân đầy đủ của lớp agent, gồm package nếu có.

Ví dụ META-INF/MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.monitor.MonitorAgent
Can-Redefine-Classes: false
Can-Retransform-Classes: true

~~~

Lớp agent cần khai báo một trong hai chữ ký premain() hợp lệ:

~~~java
package com.example.monitor;

import java.lang.instrument.Instrumentation;

public final class MonitorAgent {
    public static void premain(
            String agentArgs,
            Instrumentation instrumentation
    ) {
        System.out.println("Monitor agent started");
        System.out.println("Options: " + agentArgs);
    }
}
~~~

JVM ưu tiên gọi premain(String, Instrumentation). Nếu lớp không có chữ ký này, JVM thử premain(String). Phương thức phải là **public static**. Với Java agent không cần truy cập Instrumentation, có thể dùng chữ ký chỉ nhận String.

Nếu không có Premain-Class, lớp agent không tải được, không có phương thức premain hợp lệ hoặc premain ném lỗi không được xử lý, JVM sẽ dừng khởi động trước khi gọi main của ứng dụng.

## 4. Khai báo khả năng redefine và retransform khi thật sự cần

Manifest có thể khai báo các thuộc tính:

| Thuộc tính | Ý nghĩa | Mặc định nếu bỏ qua |
|---|---|---|
| Can-Redefine-Classes | Agent cần khả năng redefine lớp đã nạp | false |
| Can-Retransform-Classes | Agent cần khả năng retransform lớp đã nạp | false |
| Can-Set-Native-Method-Prefix | Agent cần đặt prefix cho native method | false |

Ví dụ:

~~~text
Premain-Class: com.example.monitor.MonitorAgent
Can-Retransform-Classes: true
~~~

Chỉ bật capability mà công cụ thực sự sử dụng. JVM vẫn có thể không hỗ trợ một capability; agent nên kiểm tra bằng các phương thức như **Instrumentation.isRetransformClassesSupported()** hoặc **isRedefineClassesSupported()** trước khi gọi thao tác tương ứng.

Can-Retransform-Classes: true không tự động biến mọi class thành có thể sửa. Một số class không thể sửa đổi; hãy kiểm tra **isModifiableClass(Class<?>)** và xử lý ngoại lệ theo tài liệu công cụ.

## 5. Truyền options cho Java agent

Phần sau dấu = trong -javaagent được chuyển thành một chuỗi duy nhất cho tham số agentArgs của premain(). JVM không định nghĩa cấu trúc key-value, dấu phẩy hay cách parse chuỗi này; agent tự quy định định dạng.

Ví dụ:

~~~bash
java -javaagent:tools/trace-agent.jar=service=orders,level=basic -jar application.jar
~~~

Trong ví dụ, premain() nhận chuỗi:

~~~text
service=orders,level=basic
~~~

Nếu agent yêu cầu một đường dẫn hoặc giá trị có khoảng trắng, hãy quote đối số theo quy tắc của shell đang dùng để toàn bộ tùy chọn được truyền thành một argument. Không tự thêm dấu phẩy, dấu chấm phẩy hoặc đổi tên key nếu tài liệu công cụ quy định định dạng khác.

## 6. Nạp nhiều Java agent và thứ tự khởi chạy

Có thể khai báo -javaagent nhiều lần trên cùng lệnh. Các phương thức premain() được gọi theo thứ tự agent xuất hiện trong command line, trước khi ứng dụng gọi main:

~~~bash
java -javaagent:tools/telemetry-agent.jar=service=orders -javaagent:tools/coverage-agent.jar=output=coverage.exec -jar application.jar
~~~

Trong ví dụ, telemetry agent khởi chạy trước coverage agent. Nếu agent thứ nhất thay đổi class loading hoặc bytecode, agent tiếp theo có thể quan sát kết quả đã qua các transformer trước đó. Thứ tự có thể ảnh hưởng kết quả instrumentation; hãy dùng thứ tự mà nhà cung cấp công cụ khuyến nghị.

Nếu một agent không khởi chạy được trong giai đoạn startup, JVM dừng trước main. Vì vậy, khi ứng dụng không khởi động sau khi thêm agent, hãy kiểm tra lỗi nạp JAR, manifest, tên lớp agent, chữ ký premain và options trước khi điều tra logic main của ứng dụng.

## 7. Nạp native agent bằng -agentlib

Native agent được nạp bằng tên thư viện:

~~~text
-agentlib:<libname>[=<options>]
~~~

JVM tìm thư viện theo quy tắc tên và đường dẫn của hệ điều hành:

| Hệ điều hành | Ví dụ tên file được tìm |
|---|---|
| Linux và hệ POSIX | lib<libname>.so |
| macOS | lib<libname>.dylib |
| Windows | <libname>.dll |

Với thư viện native có tên libprofiler.so trên Linux, tên libname thường là profiler:

~~~bash
java -agentlib:profiler=mode=cpu,interval=10 -jar application.jar
~~~

JVM cần tìm thấy thư viện theo cơ chế tìm kiếm thư viện native của nền tảng, ví dụ **LD_LIBRARY_PATH** trên Linux, **DYLD_LIBRARY_PATH** trên macOS hoặc **PATH** trên Windows. Hãy làm theo hướng dẫn cài đặt của công cụ để cấu hình đúng thư mục thư viện.

Với native JVMTI agent, JVM gọi entry point **Agent_OnLoad(JavaVM*, char*, void*)** trong thư viện khi khởi động. Chuỗi options được chuyển cho agent; định dạng và cách phân tích do công cụ quy định. Nếu Agent_OnLoad trả về mã lỗi, JVM kết thúc quá trình khởi động.

## 8. Dùng -agentpath khi công cụ yêu cầu đường dẫn tuyệt đối

~~~text
-agentpath:<pathname>[=<options>]
~~~

Ví dụ trên Linux:

~~~bash
java -agentpath:/opt/profiler/lib/libprofiler.so=mode=cpu -jar application.jar
~~~

Ví dụ trên Windows:

~~~powershell
java -agentpath:C:/tools/profiler/profiler.dll=mode=cpu -jar application.jar
~~~

-agentpath nạp cùng loại native agent như -agentlib, nhưng dùng đường dẫn đầy đủ và không mở rộng tên thư viện theo quy tắc tìm kiếm tên. Đường dẫn phải trỏ đến file native tương thích với hệ điều hành, kiến trúc CPU và JVM đang chạy.

## 9. Ví dụ JDWP debugger bằng -agentlib

JDWP là giao thức debugger được dùng trong Java Platform Debugger Architecture. Trên JDK 21, có thể nạp JDWP agent bằng -agentlib:jdwp:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=n -jar application.jar
~~~

Ý nghĩa các tùy chọn ví dụ:

- transport=dt_socket: dùng socket transport.
- server=y: JVM chờ debugger kết nối vào.
- address=127.0.0.1:5005: lắng nghe trên loopback interface, cổng 5005.
- suspend=n: không tạm dừng JVM chờ debugger trước khi chạy ứng dụng.

Nếu công cụ hướng dẫn dùng suspend=y, JVM sẽ tạm dừng ở giai đoạn khởi động cho đến khi debugger kết nối. Hãy dùng đúng cấu hình của IDE hoặc debugger. Không mở cổng debug ra mạng công cộng; chọn địa chỉ và quy tắc mạng phù hợp với môi trường triển khai.

## 10. Java agent và native agent khác nhau ở điểm nào?

| Tiêu chí | Java agent | Native JVMTI agent |
|---|---|---|
| Tùy chọn khởi động | -javaagent | -agentlib hoặc -agentpath |
| Artifact | JAR | DLL, .so, .dylib hoặc thư viện native tương ứng |
| Điểm vào khi startup | premain() | Agent_OnLoad() |
| API chính | java.lang.instrument.Instrumentation | JVM Tool Interface (JVMTI) |
| Cách truyền options | Một chuỗi agentArgs | Chuỗi options native |
| Phụ thuộc nền tảng | Thường ít phụ thuộc hệ điều hành hơn | Phải khớp OS, kiến trúc và ABI/runtime |

Một công cụ có thể cung cấp cả Java agent và native agent cho các mục đích khác nhau. Chọn đúng loại theo hướng dẫn của nhà cung cấp; không đổi qua lại chỉ để thử sửa lỗi nạp.

## 11. Đặt agent đúng vị trí trong lệnh chạy

Tùy chọn agent là tùy chọn của JVM, vì vậy phải đặt trước main class, -jar hoặc -m:

~~~bash
java -Xms1g -Xmx2g -javaagent:tools/monitor.jar -agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=n -jar application.jar --spring.profiles.active=prod
~~~

Trong ví dụ:

- -Xms, -Xmx, -javaagent và -agentlib là tùy chọn JVM.
- -jar application.jar xác định ứng dụng được khởi chạy.
- Đối số phía sau application.jar được truyền cho main của ứng dụng.

Nếu ứng dụng được khởi chạy bằng main class hoặc module, nguyên tắc vẫn giống nhau: đặt tùy chọn agent trong phần options của launcher, trước tên main class hoặc module.

## 12. Kiểm tra cấu hình khi agent không khởi chạy

Khi thêm agent làm ứng dụng không thể khởi động, kiểm tra theo thứ tự:

1. **Loại agent**: tài liệu công cụ yêu cầu Java agent, native agent hay debugger?
2. **Đường dẫn**: JAR hoặc native library có tồn tại và tiến trình có quyền đọc không?
3. **Tương thích nền tảng**: native library có đúng hệ điều hành, CPU architecture và JVM không?
4. **Manifest**: Java agent JAR có Premain-Class đúng tên binary class không?
5. **Điểm vào**: lớp agent có premain hợp lệ hoặc thư viện native có Agent_OnLoad không?
6. **Options**: chuỗi tham số có đúng định dạng mà công cụ quy định không?
7. **Vị trí trong command line**: tùy chọn agent có nằm trước main class hoặc -jar không?
8. **Thứ tự agent**: có xung đột hoặc phụ thuộc thứ tự giữa các agent không?
9. **Log khởi động**: đọc thông báo JVM và log của chính agent để xác định bước nạp thất bại.

Với Java agent, lỗi manifest hoặc premain thường làm JVM dừng trước main. Với native agent, lỗi tìm thư viện, thiếu dependency native hoặc Agent_OnLoad trả mã lỗi cũng có thể khiến startup thất bại.

## 13. Lưu ý bảo mật và vận hành

Agent chạy trong cùng tiến trình với ứng dụng và có thể quan sát hoặc thay đổi bytecode, trạng thái JVM theo capability được cấp. Native agent có thể thực thi mã native với quyền của tiến trình. Vì vậy:

- Chỉ nạp agent từ nhà cung cấp và nguồn phát hành đáng tin cậy.
- Xác minh file JAR hoặc thư viện native đúng phiên bản và đúng môi trường.
- Không đưa options chứa secret vào command line nếu chúng có thể bị lộ qua process listing hoặc log.
- Hạn chế quyền truy cập tới file agent và thư mục chứa native library.
- Đánh giá tác động hiệu năng và tương thích trước khi triển khai production.
- Dùng đúng cấu hình theo phiên bản JDK; không sao chép tùy chọn nội bộ hoặc lỗi thời từ hướng dẫn cũ.

## 14. Checklist khai báo agent

- [ ] Xác định rõ công cụ yêu cầu Java agent hay native agent.
- [ ] Dùng -javaagent cho agent JAR có Premain-Class.
- [ ] Dùng -agentlib cho native library theo tên hoặc -agentpath cho đường dẫn tuyệt đối.
- [ ] Đặt tùy chọn agent trước main class, -jar hoặc -m.
- [ ] Truyền options đúng định dạng được tài liệu công cụ quy định.
- [ ] Kiểm tra manifest và chữ ký premain đối với Java agent.
- [ ] Kiểm tra thư viện native đúng OS, CPU architecture và dependency.
- [ ] Chỉ bật redefine/retransform khi công cụ cần và JVM hỗ trợ.
- [ ] Kiểm tra thứ tự nếu nạp nhiều Java agent.
- [ ] Xem log startup nếu agent không nạp được.
- [ ] Xác minh nguồn gốc và quyền truy cập agent trước khi đưa vào production.

## Tài liệu tham khảo

- [Java SE 21: The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 API: java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 21 API: Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 21: JVM Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html)
- [Java SE 21 API: ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
