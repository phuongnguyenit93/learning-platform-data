# VM option trong Java launcher

## 1. VM option là gì?

Khi chạy một chương trình Java, lệnh **java** khởi động Java Virtual Machine (JVM), nạp lớp chính và gọi phương thức **main**. VM option là tùy chọn dòng lệnh dùng để cấu hình hoặc quan sát JVM trong một lần chạy. Tùy chọn có thể điều chỉnh vùng nhớ heap, bộ thu gom rác (Garbage Collector), ngăn xếp luồng, system property, assertion, ghi log và công cụ chẩn đoán.

VM option được xử lý khi JVM khởi động. Nó thường ảnh hưởng đến toàn bộ tiến trình Java, vì vậy cần đặt đúng vị trí trên dòng lệnh và hiểu rõ phạm vi của từng cờ.

Một lệnh Java có thể gồm ba nhóm thành phần:

1. **VM options**: cấu hình JVM, ví dụ **-Xmx1g**, **-Xms256m**, **-Dapp.env=dev**, **-ea**.
2. **Launcher options**: hướng dẫn Java launcher tìm và chọn chương trình, ví dụ **-cp**, **--class-path**, **-jar**, **-m**.
3. **Application arguments**: đối số được truyền vào phương thức **main(String[] args)** của chương trình.

Ba nhóm này có mục đích khác nhau. **-cp** chọn classpath, còn **-Xmx** giới hạn heap; một tùy chọn chọn cách khởi chạy ứng dụng, tùy chọn kia cấu hình bộ nhớ của JVM.

## 2. Cú pháp và vị trí của VM option

Cú pháp khái quát khi chạy một lớp:

~~~bash
java [VM options] [launcher options] <main-class> [application arguments...]
~~~

Khi chạy tệp JAR:

~~~bash
java [VM options] -jar <application.jar> [application arguments...]
~~~

Khi chạy module:

~~~bash
java [VM options] -m <module>/<main-class> [application arguments...]
~~~

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -Dapp.env=dev -ea -cp app/classes com.example.Main input.txt
~~~

Trong ví dụ này:

- **-Xms256m** đặt heap ban đầu là 256 MiB.
- **-Xmx1g** đặt giới hạn heap tối đa là 1 GiB.
- **-Dapp.env=dev** tạo system property tên **app.env** với giá trị **dev**.
- **-ea** bật kiểm tra assertion trong các lớp ứng dụng.
- **-cp app/classes** là launcher option, chỉ định nơi tìm lớp.
- **com.example.Main** là lớp chính.
- **input.txt** là đối số ứng dụng, xuất hiện trong **args**.

Với chế độ JAR, các VM option phải đứng trước **-jar** và tên JAR:

~~~bash
java -Xmx512m -Dapp.env=prod -jar app.jar --port 8080
~~~

Ở đây **--port 8080** được truyền cho ứng dụng. Nếu viết **-Dapp.env=prod** sau **app.jar**, token đó cũng trở thành đối số ứng dụng; nó không còn được JVM xử lý như một system property.

Tương tự, trong chế độ chạy lớp, mọi token sau tên lớp được truyền vào **main**. Vì vậy, hãy đặt VM option trước tên lớp, tên JAR hoặc module được chạy.

Khi dùng **-jar**, JAR được chọn làm nguồn lớp và điểm vào ứng dụng theo thuộc tính **Main-Class** trong manifest. Classpath bên ngoài được cấu hình bằng **-cp** không thay thế classpath của chế độ **-jar**. Nếu cần tự chỉ định classpath, thường chạy lớp chính bằng **-cp** thay vì dùng **-jar**.

## 3. Các nhóm tùy chọn thường gặp

### Tùy chọn chuẩn

Một số tùy chọn được Java launcher hỗ trợ rộng rãi:

| Tùy chọn | Ý nghĩa |
|---|---|
| **-Dname=value** | Đặt system property |
| **-ea** hoặc **-enableassertions** | Bật assertion |
| **-da** hoặc **-disableassertions** | Tắt assertion |
| **-esa** | Bật system assertion |
| **-dsa** | Tắt system assertion |
| **-verbose:gc** | Hiển thị thông tin GC theo dạng verbose cũ |
| **-agentlib:...** | Nạp native agent theo tên thư viện |
| **-agentpath:...** | Nạp native agent theo đường dẫn |
| **-javaagent:...** | Nạp Java instrumentation agent |

### Tùy chọn mở rộng -X

Các tùy chọn bắt đầu bằng **-X** thường được gọi là tùy chọn mở rộng hoặc không chuẩn. Chúng được hỗ trợ bởi một số JVM cụ thể và có thể thay đổi theo nhà cung cấp hoặc phiên bản. Các ví dụ quen thuộc gồm **-Xms**, **-Xmx**, **-Xss**, **-Xlog** và **-Xint**.

### Tùy chọn nâng cao -XX

Các tùy chọn bắt đầu bằng **-XX** thường điều khiển các cờ nâng cao của HotSpot. Cú pháp phổ biến:

~~~text
-XX:+FlagName
-XX:-FlagName
-XX:FlagName=value
~~~

- **-XX:+FlagName** bật một cờ boolean.
- **-XX:-FlagName** tắt một cờ boolean.
- **-XX:FlagName=value** gán giá trị cho cờ.

Ví dụ:

~~~bash
java -XX:+UseG1GC -Xmx1g -jar app.jar
~~~

Các cờ **-XX** không phải hợp đồng tương thích chung cho mọi JVM. Một cờ có thể không tồn tại hoặc có ý nghĩa khác trên một nhà cung cấp hay phiên bản khác. Hãy kiểm tra tài liệu đúng phiên bản JDK đang chạy trước khi dùng trong môi trường triển khai.

## 4. Cấu hình bộ nhớ JVM

### Heap ban đầu và heap tối đa

Heap là vùng nhớ JVM dùng để cấp phát phần lớn đối tượng Java. Hai tùy chọn cơ bản:

- **-Xms<size>**: kích thước heap ban đầu.
- **-Xmx<size>**: kích thước heap tối đa.

Ví dụ:

~~~bash
java -Xms256m -Xmx2g -jar app.jar
~~~

JVM khởi động với heap ban đầu 256 MiB và được phép mở rộng đến tối đa 2 GiB. Kích thước heap thực tế và cách JVM sử dụng vùng nhớ còn phụ thuộc phiên bản, nền tảng và điều kiện chạy.

Các hậu tố thường dùng:

| Hậu tố | Đơn vị |
|---|---|
| **k** hoặc **K** | KiB, bội số 1024 byte |
| **m** hoặc **M** | MiB, bội số 1024 KiB |
| **g** hoặc **G** | GiB, bội số 1024 MiB |

Ví dụ **-Xmx512m** đặt heap tối đa 512 MiB; **-Xmx2g** đặt tối đa 2 GiB. Nếu không ghi hậu tố, giá trị số được hiểu theo byte. Hãy bảo đảm **-Xms** không lớn hơn **-Xmx**.

### Heap không phải toàn bộ bộ nhớ tiến trình

**-Xmx** giới hạn heap, không giới hạn toàn bộ RAM mà tiến trình Java có thể sử dụng. Tiến trình còn cần bộ nhớ cho:

- Metaspace lưu metadata của lớp.
- Code cache chứa mã máy do JIT compiler sinh ra.
- Stack của từng luồng Java.
- Direct buffer, thư viện native và cấu trúc nội bộ của JVM.
- Bộ nhớ dành cho agent và các thành phần native khác.

Do đó, tiến trình có thể bị hệ điều hành hoặc container kết thúc dù heap chưa chạm **-Xmx**. Khi đặt giới hạn heap cho container, cần chừa dung lượng cho native memory, thread stack, JVM overhead và các tiến trình khác.

### Stack của luồng

**-Xss<size>** đặt kích thước stack cho mỗi luồng Java:

~~~bash
java -Xss1m -jar app.jar
~~~

Stack giữ khung gọi phương thức, biến cục bộ và thông tin thực thi của luồng. Stack quá nhỏ có thể dẫn đến **StackOverflowError** khi độ sâu gọi hàm lớn; stack quá lớn làm tăng nhu cầu bộ nhớ native khi ứng dụng tạo nhiều luồng. Chỉ thay đổi giá trị này khi đã hiểu đặc điểm của ứng dụng và có số liệu kiểm tra.

### Metaspace và direct memory

Một số giới hạn nâng cao có thể hữu ích khi chẩn đoán:

~~~bash
java -XX:MaxMetaspaceSize=256m -XX:MaxDirectMemorySize=512m -jar app.jar
~~~

**MaxMetaspaceSize** đặt giới hạn cho Metaspace; **MaxDirectMemorySize** đặt giới hạn cho bộ nhớ direct buffer được JVM quản lý. Đây là các cờ HotSpot và không nên đặt tùy tiện. Giới hạn quá thấp có thể làm ứng dụng lỗi khi nạp nhiều lớp hoặc cấp phát nhiều direct buffer.

## 5. Chọn Garbage Collector

Garbage Collector thu hồi vùng heap mà chương trình không còn tham chiếu đến. JVM cung cấp nhiều bộ thu gom rác với đặc điểm khác nhau về thông lượng, độ trễ và mức tiêu thụ tài nguyên.

Ví dụ trên HotSpot:

~~~bash
java -XX:+UseG1GC -jar app.jar
~~~

Cờ **-XX:+UseG1GC** yêu cầu dùng G1 Garbage Collector. Một lựa chọn khác trên các bản HotSpot hỗ trợ là:

~~~bash
java -XX:+UseSerialGC -jar app.jar
~~~

Không có một bộ thu gom rác tối ưu cho mọi ứng dụng. Lựa chọn phụ thuộc kích thước heap, số lõi CPU, mục tiêu độ trễ, thông lượng và đặc điểm cấp phát đối tượng. JVM có thể chọn bộ thu gom mặc định dựa trên nền tảng và cấu hình; không nên thay mặc định chỉ vì thấy một cờ trong ví dụ.

Khi cần quyết định, hãy đo thời gian tạm dừng, thông lượng và mức sử dụng CPU trên workload đại diện. Ghi lại phiên bản JDK và toàn bộ cờ đang dùng để có thể so sánh các lần thử một cách công bằng.

## 6. System property với -D

Tùy chọn **-Dname=value** đặt một system property khi JVM khởi động:

~~~bash
java -Dapp.env=dev -Dapp.region=ap-southeast-1 -jar app.jar
~~~

Ứng dụng đọc giá trị bằng API **System.getProperty**:

~~~java
String environment = System.getProperty("app.env");
String region = System.getProperty("app.region", "unknown");
~~~

System property là cặp tên và giá trị dạng chuỗi trong JVM. Nó khác biến môi trường của hệ điều hành:

- **System.getProperty("app.env")** đọc system property được đặt bằng **-D** hoặc qua API Java.
- **System.getenv("APP_ENV")** đọc biến môi trường do hệ điều hành cung cấp.

Không nhầm **-Dapp.env=dev** với việc tạo biến môi trường **APP_ENV**. Tên property phân biệt chữ hoa và chữ thường. Nếu giá trị có dấu cách hoặc ký tự đặc biệt, hãy đặt token trong dấu nháy theo quy tắc của shell đang dùng.

Trong PowerShell, nên đặt toàn bộ token **-D** trong dấu nháy đơn để PowerShell chuyển nguyên token cho Java:

~~~powershell
java '-Dapp.env=dev' -jar app.jar
~~~

Không đưa mật khẩu, token hoặc thông tin bí mật vào system property trên dòng lệnh. Thông tin dòng lệnh có thể xuất hiện trong danh sách tiến trình, log hoặc công cụ chẩn đoán tùy môi trường.

## 7. Bật và tắt assertion

Java assertion cho phép kiểm tra giả định trong lúc phát triển và kiểm thử. Assertion bị tắt mặc định khi chạy chương trình thông thường.

Bật tất cả assertion trong các lớp ứng dụng:

~~~bash
java -ea -jar app.jar
~~~

Tắt assertion:

~~~bash
java -da -jar app.jar
~~~

Có thể bật theo package hoặc lớp:

~~~bash
java -ea:com.example... -jar app.jar
java -ea:com.example.OrderService -jar app.jar
~~~

Dạng package với dấu ba chấm áp dụng cho package và các package con. Dạng tên lớp áp dụng cho lớp được chỉ định. Tùy chọn **-esa** bật assertion trong các lớp hệ thống; **-dsa** tắt chúng.

Trong mã Java:

~~~java
int quantity = 3;
assert quantity > 0 : "quantity must be positive";
~~~

Khi assertion được bật, điều kiện sai sẽ ném **AssertionError** và có thể kèm thông điệp. Không dùng assertion để thay thế kiểm tra dữ liệu đầu vào từ người dùng hoặc kiểm tra bắt buộc trong production, vì assertion có thể bị tắt. Với kiểm tra nghiệp vụ bắt buộc, hãy dùng điều kiện và xử lý lỗi tường minh.

## 8. Logging và chẩn đoán JVM

### Unified logging

Từ Java 9, JVM có hệ thống unified logging. Với JDK hiện đại, có thể bật log GC bằng:

~~~bash
java -Xlog:gc -jar app.jar
~~~

Ghi log GC ra tệp với thời gian và nhãn:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

**-Xlog** có cú pháp chọn tag, mức log, output và decorator. Dấu **\*** sau **gc** chọn các tag GC phù hợp. Có thể xem hướng dẫn cú pháp trên chính JDK đang dùng bằng **java -Xlog:help**. Log GC giúp phân tích chu kỳ thu gom, thời gian tạm dừng và hoạt động của heap; log quá chi tiết có thể tạo nhiều dữ liệu và ảnh hưởng hiệu năng.

### Heap dump khi hết bộ nhớ

Có thể yêu cầu JVM tạo heap dump khi xảy ra **OutOfMemoryError**:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps -jar app.jar
~~~

Đường dẫn đích phải ghi được; hãy tạo thư mục **dumps** trước khi chạy nếu chưa tồn tại. Heap dump có thể chứa dữ liệu nhạy cảm mà ứng dụng đang giữ trong bộ nhớ. Hãy bảo vệ tệp, giới hạn quyền truy cập và xóa theo chính sách lưu trữ sau khi hoàn tất phân tích.

### Java agent và công cụ debug

**-javaagent:path/to/agent.jar** nạp Java instrumentation agent. Agent có thể quan sát hoặc biến đổi bytecode khi lớp được nạp, ví dụ cho công cụ giám sát, profiling hoặc kiểm thử.

**-agentlib** và **-agentpath** nạp native agent. Để mở giao thức debug JDWP trong môi trường phát triển, ví dụ:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Tùy chọn này mở cổng debug trên địa chỉ loopback. **suspend=n** cho phép ứng dụng tiếp tục chạy thay vì chờ debugger kết nối. Chỉ bật debug agent khi cần thiết và kiểm soát được môi trường cũng như địa chỉ lắng nghe.

## 9. Chương trình mẫu kiểm tra VM option

Tạo tệp **VmOptionsDemo.java**:

~~~java
public class VmOptionsDemo {
    public static void main(String[] args) {
        String environment = System.getProperty("app.env", "not-set");
        long maxHeapMiB =
                Runtime.getRuntime().maxMemory() / (1024 * 1024);

        System.out.println("app.env=" + environment);
        System.out.println("maxHeapMiB=" + maxHeapMiB);
        System.out.println("assertions="
                + VmOptionsDemo.class.desiredAssertionStatus());
        System.out.println("argCount=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=" + args[i]);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac VmOptionsDemo.java
~~~

Chạy trên Linux hoặc macOS:

~~~bash
java -Xms64m -Xmx256m -Dapp.env=dev -ea -cp . VmOptionsDemo one two
~~~

Chạy trong PowerShell:

~~~powershell
java -Xms64m -Xmx256m '-Dapp.env=dev' -ea -cp . VmOptionsDemo one two
~~~

Kết quả:

~~~text
app.env=dev
maxHeapMiB=256
assertions=true
argCount=2
arg[0]=one
arg[1]=two
~~~

Chương trình cho thấy ba tác động khác nhau:

- **System.getProperty** đọc giá trị do **-Dapp.env=dev** đặt.
- **Runtime.getRuntime().maxMemory()** phản ánh giới hạn heap tối đa mà JVM báo cho ứng dụng; với ví dụ này là 256 MiB.
- **desiredAssertionStatus()** cho biết assertion của lớp đang bật hay tắt.

Các từ **one** và **two** nằm sau tên lớp nên trở thành phần tử của mảng **args**. Nếu thay **-ea** bằng **-da**, dòng assertion sẽ là **assertions=false**. Nếu bỏ **-Dapp.env=dev**, giá trị mặc định trong chương trình sẽ là **not-set**.

## 10. Tra cứu và kiểm tra các cờ đang hoạt động

Mỗi phiên bản JDK có tập tùy chọn riêng. Dùng các lệnh sau để xem hướng dẫn từ chính launcher:

~~~bash
java -help
java -X
java -XX:+PrintFlagsFinal -version
java -XshowSettings:vm -version
~~~

- **java -help** liệt kê các tùy chọn launcher và tùy chọn chuẩn.
- **java -X** hiển thị nhóm tùy chọn mở rộng được JVM hỗ trợ.
- **-XX:+PrintFlagsFinal** in các cờ HotSpot và giá trị cuối cùng sau khi khởi tạo; kết quả khá dài.
- **-XshowSettings:vm** hiển thị thông tin cấu hình VM rồi in phiên bản.

Với một tiến trình đang chạy, JDK cung cấp **jcmd** để xem thông tin. Trước tiên liệt kê các tiến trình Java:

~~~bash
jcmd -l
~~~

Sau đó dùng PID của tiến trình cần kiểm tra:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

**VM.command_line** hiển thị dòng lệnh khởi chạy; **VM.flags** hiển thị cờ VM đang áp dụng. Các lệnh này thường yêu cầu cùng tài khoản người dùng và cơ chế attach của JVM phải khả dụng. **jcmd** là công cụ của JDK; máy chỉ cài runtime tối giản có thể không có công cụ này.

## 11. Lỗi thường gặp và cách xử lý

### Unrecognized VM option

JVM báo không nhận diện tùy chọn. Nguyên nhân có thể là:

- Cờ không được hỗ trợ bởi nhà cung cấp JVM đang dùng.
- Cờ đã bị loại bỏ hoặc thay đổi trong phiên bản mới.
- Sai chính tả, sai cú pháp hoặc thiếu giá trị.
- Dùng cờ HotSpot trên một JVM có tập cờ khác.

Hãy kiểm tra **java -version**, **java -X**, tài liệu của đúng nhà cung cấp và phiên bản JDK. Không sao chép nguyên một bộ cờ từ máy khác mà chưa xác minh.

### Could not create the Java Virtual Machine

Thông báo này thường đi kèm lỗi tùy chọn không hợp lệ, kích thước bộ nhớ không phù hợp hoặc cấu hình xung đột. Đọc các dòng lỗi ngay phía trên để tìm cờ gây lỗi. Thử bỏ lần lượt tùy chọn mới thêm trong môi trường kiểm thử để xác định nguyên nhân.

### OutOfMemoryError dù đã đặt -Xmx

**-Xmx** chỉ giới hạn heap. **OutOfMemoryError** cũng có thể liên quan đến Metaspace, direct buffer hoặc tài nguyên khác. Ngoài ra, hệ điều hành hoặc container có thể kết thúc tiến trình vì tổng mức sử dụng bộ nhớ vượt giới hạn trước khi heap chạm **-Xmx**. Cần xác định loại lỗi và xem log, heap dump hoặc số liệu native memory trước khi tăng giới hạn.

### VM option không có tác dụng

Kiểm tra thứ tự token trên dòng lệnh. VM option phải đứng trước tên lớp, **-jar** hoặc **-m**. Kiểm tra thêm cấu hình chạy trong IDE, script khởi động, service manager và biến môi trường như **JDK_JAVA_OPTIONS** hoặc **JAVA_TOOL_OPTIONS**, vì chúng có thể đưa thêm tùy chọn vào tiến trình.

Trong IDE, phân biệt trường **VM options** với **Program arguments**. Nếu nhập **-Xmx** vào Program arguments, ứng dụng sẽ nhận chuỗi đó như đối số thông thường và heap không thay đổi.

### Cấu hình quá nhiều cờ

Việc thêm nhiều cờ **-XX** không đồng nghĩa JVM chạy nhanh hơn. Một số cờ có thể xung đột, làm mất khả năng dùng tối ưu mặc định hoặc chỉ phù hợp với workload cụ thể. Bắt đầu từ cấu hình mặc định, đo đạc bằng dữ liệu thực tế, thay đổi từng nhóm cờ và lưu lại kết quả để có thể quay lại cấu hình đã biết.

## 12. Checklist khi sử dụng VM option

- [ ] Xác định đúng JVM và phiên bản bằng **java -version**.
- [ ] Phân biệt VM option, launcher option và application argument.
- [ ] Đặt VM option trước tên lớp, **-jar** hoặc **-m**.
- [ ] Dùng **-Xms** và **-Xmx** có chủ đích; chừa bộ nhớ cho native memory và môi trường chạy.
- [ ] Chỉ thay đổi GC hoặc cờ **-XX** khi có tài liệu và số liệu kiểm chứng.
- [ ] Dùng **-D** cho system property và **System.getenv** cho biến môi trường.
- [ ] Bật assertion bằng **-ea** trong kiểm thử khi cần; không dựa vào assertion cho kiểm tra bắt buộc.
- [ ] Dùng **-Xlog** và heap dump để thu thập bằng chứng khi chẩn đoán.
- [ ] Kiểm tra cờ thực tế bằng **jcmd** hoặc **PrintFlagsFinal** khi cần.
- [ ] Ghi lại các cờ đã dùng cùng phiên bản JDK để tái lập kết quả.
