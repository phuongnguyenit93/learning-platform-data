# Phân biệt tham số JVM, thuộc tính hệ thống và đối số của ứng dụng

## 1. Mục tiêu và ngữ cảnh

Khi khởi chạy một chương trình Java, nhiều thông tin có thể xuất hiện trên cùng một dòng lệnh: giới hạn bộ nhớ, lựa chọn classpath, giá trị cấu hình, đường dẫn tệp đầu vào, chế độ hoạt động và cờ riêng của chương trình. Chúng trông giống nhau vì cùng là các chuỗi ký tự trong terminal, nhưng **khác nhau về người xử lý, thời điểm xử lý, phạm vi ảnh hưởng và API truy cập**.

Sau bài học, bạn cần:

- Phân biệt **tùy chọn khởi chạy Java/JVM** (launcher/VM options), **thuộc tính hệ thống Java** (system properties) và **đối số ứng dụng** (application arguments).
- Đặt đúng vị trí các tham số trong lệnh **java**, hiểu chính xác vai trò của **-D**.
- Đọc system property bằng **System.getProperty(...)** và đọc đối số thông qua **String[] args**.
- Hiểu cấu hình nào phải áp dụng khi tạo JVM, cấu hình nào có thể thay đổi khi chương trình đang chạy.
- Chẩn đoán tình huống tham số bị chuyển nhầm vào **args**, giá trị không được áp dụng hoặc phụ thuộc vào shell, công cụ build và môi trường.

Bài học tập trung vào quá trình khởi động một tiến trình Java. Một ứng dụng, framework hoặc script khởi chạy có thể tự định nghĩa quy tắc cấu hình bổ sung, nhưng các quy tắc đó phải được nhận diện riêng.

## 2. Một dòng lệnh, ba loại thông tin

Cú pháp phổ biến khi gọi một lớp có phương thức **main** là:

~~~text
java [tùy chọn của java/VM] <TênLớpMain> [đối số ứng dụng...]

Ví dụ:
java -Xmx256m -Ddemo.mode=dev -cp out Main --input=data.csv
     |       |              |       |    |
     |       |              |       |    +-- đối số của ứng dụng
     |       |              |       +------- tên lớp main
     |       |              +--------------- classpath cho Java launcher
     |       +------------------------------ tùy chọn đặt system property
     +-------------------------------------- tùy chọn cấu hình VM
~~~

Điểm phân cách là **tên lớp main** (hoặc đích khởi chạy như **-jar app.jar**). Những token ở phía sau đích khởi chạy được chuyển vào chương trình làm đối số ứng dụng. Java launcher xử lý các tùy chọn của mình trước khi gọi **main(String[] args)**. Shell cũng có giai đoạn xử lý dấu nháy, khoảng trắng và escape trước khi tiến trình **java** nhận được các token.

| Loại | Ví dụ | Ai xử lý trực tiếp? | Cách truy cập/quan sát |
| --- | --- | --- | --- |
| **Tùy chọn JVM/Java launcher** | **-Xmx256m**, **-ea**, **-cp out**, **-XX:+UseG1GC** | Java launcher và/hoặc VM khi khởi động | Hành vi VM, công cụ quản trị/quan sát; không nằm trong **args** nếu đặt đúng chỗ |
| **System property** | **-Ddemo.mode=dev** tạo property **demo.mode** với giá trị **dev** | Tùy chọn **-D** được launcher xử lý, sau đó JVM cung cấp property cho chương trình | **System.getProperty("demo.mode")** |
| **Đối số ứng dụng** | **--input=data.csv**, **--dry-run**, **report.csv** | **main(...)** hoặc framework/parser do ứng dụng dùng | **String[] args** |

**Quan hệ quan trọng:** **-D** vừa là **cú pháp tùy chọn của lệnh java**, vừa là cách **khởi tạo một system property**. “System property” là dữ liệu cấu hình nằm trong tiến trình Java; nó không phải một dạng tùy chọn tinh chỉnh VM như **-Xmx**. Không nên ép ba nhóm thành các tập hoàn toàn không giao nhau ở cấp độ cú pháp.

Tương tự, **-cp** là tùy chọn của **Java launcher** quyết định nơi tìm class, chứ không phải tham số điều chỉnh heap. Trong giao tiếp hằng ngày, các tùy chọn đặt trước main đôi khi đều được gọi chung là “tham số JVM”; khi phân tích lỗi cần phân biệt **tùy chọn VM** với **tùy chọn launcher**.

## 3. JVM options: cấu hình quá trình khởi chạy

Các tùy chọn này được tiêu thụ khi Java launcher/JVM chuẩn bị tiến trình, và thường không được chuyển cho **main(String[] args)**.

### 3.1. Ví dụ tiêu biểu

| Tùy chọn | Ý nghĩa thực tế | Ghi chú |
| --- | --- | --- |
| **-Xms128m** | Yêu cầu kích thước heap ban đầu | Tùy chọn phổ biến của HotSpot; việc cấp phát bộ nhớ vật lý thực tế phụ thuộc VM/OS |
| **-Xmx512m** | Đặt giới hạn kích thước heap tối đa cho Java heap | Không đồng nghĩa giới hạn toàn bộ RAM tiến trình; còn metaspace, stacks, native memory... |
| **-ea** hoặc **-enableassertions** | Bật assertion theo phạm vi mặc định/quy định của tùy chọn | Chỉ có tác dụng với các câu lệnh **assert**; không thay thế kiểm tra dữ liệu đầu vào |
| **-XX:+UseG1GC** | Chọn G1 GC trên HotSpot hỗ trợ tùy chọn này | Thuộc nhóm tùy chọn VM mang tính triển khai; cần kiểm tra JDK/VM đang dùng |
| **-cp out** hoặc **-classpath out** | Chỉ định classpath khi chạy lớp main | Do launcher xử lý; cú pháp và ý nghĩa khác với các tham số ứng dụng |
| **-Dapp.region=apac** | Đặt system property **app.region** | Là tùy chọn launcher để cung cấp dữ liệu thuộc tính cho Java |

Những tùy chọn bắt đầu bằng **-X** hoặc **-XX** không nên được mặc định xem là ổn định trên mọi phiên bản và mọi nhà cung cấp JVM. Cờ có thể không được hỗ trợ, đổi tên hoặc đổi ý nghĩa giữa các runtime. Khi một cờ không hợp lệ, chương trình có thể kết thúc **trước khi main được gọi**.

### 3.2. Thời điểm áp dụng và phạm vi

Các cấu hình như giới hạn heap hoặc chọn GC phải được thiết lập khi khởi động JVM tương ứng. Gọi:

~~~java
// Mã minh họa, không phải chương trình Java độc lập.
System.setProperty("Xmx", "1g");
~~~

**không** tăng heap tối đa lên 1 GB, bởi **Xmx** trong ví dụ chỉ là tên một system property tự tạo; JVM không diễn giải property đó thành tùy chọn **-Xmx**. Tương tự, chuỗi **"-Xmx1g"** xuất hiện trong **args** không tự thay đổi VM.

Một VM đang chạy có thể hỗ trợ những cơ chế quản trị động nhất định (phụ thuộc triển khai/cờ), nhưng điều đó không khiến tất cả startup options trở thành cấu hình có thể thay đổi bằng Java API.

## 4. System properties: bảng tên–giá trị trong tiến trình Java

**System properties** là tập cặp khóa/giá trị chuỗi do lớp **java.lang.System** cung cấp. Có property do runtime thiết lập, như **java.version**, **os.name**, **user.dir**; cũng có property do người khởi chạy đặt, ví dụ **demo.profile**, **app.port**.

Các thao tác thường dùng:

~~~java
// Các dòng minh họa đặt trong một phương thức Java.
String profile = System.getProperty("demo.profile");
String fallback = System.getProperty("demo.profile", "local");
System.setProperty("demo.profile", "test");
System.clearProperty("demo.profile");
~~~

- **System.getProperty(key)** trả về giá trị hiện có; khi khóa không tồn tại, kết quả là **null**.
- **System.getProperty(key, defaultValue)** trả về giá trị mặc định nếu khóa không có.
- **System.setProperty(key, value)** đổi giá trị trong cùng tiến trình JVM, trả về giá trị cũ hoặc **null** nếu trước đó chưa có; các phần khác trong tiến trình có thể quan sát thấy thay đổi.
- **System.clearProperty(key)** xóa property và trả về giá trị cũ nếu có.
- Java cũng cho phép truy cập tập properties qua **System.getProperties()**; không nên in toàn bộ tập này ra log khi có thể chứa dữ liệu nhạy cảm.

**-Ddemo.profile=dev** là cách thông dụng để khởi tạo property trước khi **main** chạy:

~~~bash
java -Ddemo.profile=dev Main
~~~

Tên **demo.profile** do ứng dụng tự chọn; JVM không biết “dev” nghĩa là gì nếu không có thành phần nào đọc property ấy. **-D** tự nó không tạo một hệ thống cấu hình có phân cấp, kiểu dữ liệu, validation hay cơ chế reload.

### 4.1. Thuộc tính không đồng nghĩa tùy chọn VM

Hãy so sánh:

~~~text
-Xmx512m                   JVM xử lý để đặt giới hạn heap
-Ddemo.maxItems=512        Tạo property tên demo.maxItems, giá trị chuỗi "512"
--max-items=512            Đối số ứng dụng nếu đặt sau main/JAR
~~~

Ba dòng này không thay thế được cho nhau. Application phải tự đọc, chuyển kiểu và kiểm tra **demo.maxItems**, còn **--max-items=512** chỉ có ý nghĩa nếu chính ứng dụng hoặc framework hiểu nó.

Một system property có thể được thay đổi lúc chạy, nhưng **không có bảo đảm** tất cả thư viện sẽ tự đọc lại giá trị mới. Một thư viện có thể đã chụp giá trị khi khởi tạo; JVM/OS cũng có những cấu hình được xác định từ trước khi **main** bắt đầu. Tránh dựa vào việc đổi property runtime để thay đổi hành vi hệ thống đã khởi tạo.

### 4.2. Thuộc tính hệ thống khác biến môi trường

Đây là hai kho dữ liệu khác nhau:

| Nội dung | System property | Environment variable |
| --- | --- | --- |
| API đọc | **System.getProperty("demo.profile")** | **System.getenv("DEMO_PROFILE")** |
| Nguồn phổ biến | Java launcher **-D**, runtime, code Java | Môi trường tiến trình do OS, shell, container hoặc process launcher truyền vào |
| Phạm vi | Trong JVM; có thể được mã Java thay đổi qua System API | Environment mà tiến trình nhận khi khởi động; Java không có API chuẩn để sửa environment của tiến trình theo cách tương đương **setProperty** |
| Quy ước tên | Ví dụ **demo.profile** | Ví dụ **DEMO_PROFILE** |
| Tự động ánh xạ giữa hai bên? | **Không** | **Không** |

Ví dụ, việc thiết lập biến môi trường **DEMO_PROFILE=dev** không khiến **System.getProperty("demo.profile")** tự trả về **dev**. Nếu muốn có quy tắc ánh xạ, ứng dụng hoặc framework phải lập trình điều đó.

Biến môi trường **JAVA_TOOL_OPTIONS** hoặc **JDK_JAVA_OPTIONS** là một trường hợp riêng: chúng có thể tác động tới JVM/launcher theo quy tắc của runtime, nhưng chúng vẫn **không** phải system properties và không đồng nghĩa với đối số ứng dụng. Chúng có giới hạn riêng và có thể khiến cờ xuất hiện “bất ngờ” dù không được gõ trực tiếp trên dòng lệnh.

## 5. Application arguments: dữ liệu được chuyển cho main

Với lớp Java truyền thống:

~~~java
public static void main(String[] args) {
    // args chứa các token nằm sau tên lớp main trong lệnh java.
}
~~~

Phần tử **args[0]** là đối số đầu tiên của chương trình, **không phải** tên lớp main, không phải **java**, và không chứa các tùy chọn JVM đã được launcher xử lý đúng vị trí.

Ví dụ:

~~~bash
java Main --mode=batch input.csv
~~~

Nếu chương trình được khởi chạy thành công, **args** có hai phần tử: **"--mode=batch"** và **"input.csv"**. Java SE không tự quy định ý nghĩa của **--mode**, **--input**, **--dry-run** hay **--port** trong **args**; đó là cú pháp do ứng dụng hoặc thư viện CLI thiết kế.

Các đối số thường phục vụ việc chọn chế độ chạy, tệp đầu vào, tác vụ, cổng nghiệp vụ và tùy chọn một lần cho quá trình chạy. Không nên tự suy luận rằng mọi đối số có dấu gạch ngang đều là JVM option.

### 5.1. Shell quyết định cách tạo ra từng token

Ví dụ:

~~~bash
java Main "first report.csv"
~~~

Với shell thông dụng hỗ trợ cú pháp nháy kép này, đối số ứng dụng là **một chuỗi** có chứa khoảng trắng: **first report.csv**. Nếu bỏ dấu nháy, shell có thể tách thành **hai** đối số là **first** và **report.csv**. Quy tắc escape và quoting chi tiết khác nhau giữa PowerShell, Command Prompt, Bash và môi trường container; khi cần tính khả chuyển, hãy kiểm tra shell đích.

Một số công cụ như IDE, Gradle hay container runtime có hai trường cấu hình tách biệt cho **VM options** và **program arguments**. Điền đúng giá trị nhưng sai trường vẫn có thể khiến Java nhận sai loại thông tin.

## 6. Ví dụ chạy được: quan sát cả ba loại

Tạo tệp **ConfigLayersDemo.java** (Java 17+):

~~~java
public class ConfigLayersDemo {
    public static void main(String[] args) {
        String profile = System.getProperty("demo.profile", "(unset)");
        String retries = System.getProperty("demo.retries", "(unset)");

        System.out.println("profile=" + profile);
        System.out.println("retries=" + retries);
        System.out.println("argCount=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=" + args[i]);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ConfigLayersDemo.java
java -Xmx256m -Ddemo.profile=dev -Ddemo.retries=3 ConfigLayersDemo --mode=batch report.csv
~~~

**Stdout chính xác của chương trình:**

~~~text
profile=dev
retries=3
argCount=2
arg[0]=--mode=batch
arg[1]=report.csv
~~~

Tại sao?

1. **-Xmx256m** được JVM xử lý trước khi gọi **main**. Nó không xuất hiện trong **args** và chương trình này không in giới hạn heap.
2. **-Ddemo.profile=dev** và **-Ddemo.retries=3** được dùng để đặt system properties. Hai lệnh **System.getProperty(...)** đọc ra chuỗi tương ứng.
3. **ConfigLayersDemo** là đích khởi chạy; Java launcher nạp lớp này và gọi **main**.
4. Hai token theo sau đích khởi chạy là **--mode=batch** và **report.csv**, được giữ nguyên trong **args**. Chương trình chỉ in chúng, chưa có logic xử lý chế độ batch hay đọc tệp.

### 6.1. Cùng chuỗi -D nhưng khác vị trí

Chạy:

~~~bash
java ConfigLayersDemo -Ddemo.profile=dev
~~~

**Stdout chính xác:**

~~~text
profile=(unset)
retries=(unset)
argCount=1
arg[0]=-Ddemo.profile=dev
~~~

Ở đây, **-Ddemo.profile=dev** đứng **sau** tên lớp main nên là dữ liệu của chương trình. Java không đặt property **demo.profile** trong trường hợp này. Lời giải chính xác là di chuyển **-D** lên trước **ConfigLayersDemo**, thay vì thay đổi code đọc property. Hai output trong mục này giả định không có cấu hình môi trường khác đặt sẵn hai property demo và không có mã ngoài ví dụ sửa chúng.

### 6.2. Sai vị trí của -Xmx

~~~bash
java ConfigLayersDemo -Xmx256m
~~~

Trong lệnh này, **-Xmx256m** được truyền vào **args[0]**; heap không được cấu hình theo token đó. Ngược lại:

~~~bash
java -Xmx256m ConfigLayersDemo
~~~

mới yêu cầu JVM đặt giới hạn heap tối đa tương ứng. Đừng xác nhận kích thước heap chính xác bằng cách lấy một số cứng từ output: VM có thể làm tròn/điều chỉnh giá trị và toàn bộ bộ nhớ tiến trình bao gồm nhiều vùng ngoài Java heap.

## 7. Với file JAR, điểm phân cách nằm ở đâu?

Ứng dụng đóng gói thành JAR có thể được khởi chạy theo cú pháp:

~~~text
java [tùy chọn launcher/JVM] -jar application.jar [đối số ứng dụng...]
~~~

**-jar** cùng đường dẫn **application.jar** chọn artifact chạy, thường dựa vào **Main-Class** trong manifest để tìm main class. Đây là cú pháp minh họa; muốn chạy được, JAR thực tế phải có main class hợp lệ và những dependency cần thiết.

Ví dụ đặt đúng vị trí:

~~~bash
java -Xmx512m -Ddemo.profile=prod -jar application.jar --mode=batch input.csv
~~~

- JVM nhận yêu cầu heap **-Xmx512m**.
- System property **demo.profile** được khởi tạo với **prod**.
- Ứng dụng nhận **--mode=batch** và **input.csv** theo cơ chế đối số của main.

So sánh lệnh:

~~~bash
java -jar application.jar -Xmx512m -Ddemo.profile=prod
~~~

Hai token phía sau **application.jar** là đối số ứng dụng. Chúng **không tự động** cấu hình heap hoặc property. Nếu framework cố tình phân tích chuỗi dạng **-D...** như một quy ước riêng, đó là logic ứng dụng, không phải hành vi mặc định của Java launcher.

**Lưu ý:** Khi khởi chạy bằng **-jar**, tùy chọn classpath **-cp** không được dùng theo cùng cách như khi chạy một lớp main trực tiếp; việc tìm class trong JAR dựa vào cơ chế riêng của launcher và metadata/dependency. Không xem **-jar** chỉ đơn giản là thay tên lớp trong mọi trường hợp.

## 8. Ứng dụng tự quy định cách diễn giải args và độ ưu tiên

**String[] args** chỉ chứa chuỗi. Java không tự chuyển **--port=8081** thành số nguyên, không tự xác minh cổng nằm trong khoảng hợp lệ và không tự quyết định **args** hay **-Ddemo.port** được ưu tiên. Ứng dụng cần nêu quy tắc.

Ví dụ độc lập tiếp theo dùng chiến lược cụ thể: mặc định **8080**, nếu có system property **demo.port** thì lấy nó, và nếu có đối số **--port=...** thì đối số được ưu tiên. Tham số **--dry-run** bật chế độ chạy thử.

Tạo **ApplicationArgsDemo.java**:

~~~java
public class ApplicationArgsDemo {
    public static void main(String[] args) {
        int port = Integer.parseInt(System.getProperty("demo.port", "8080"));
        boolean dryRun = false;

        for (String arg : args) {
            if (arg.startsWith("--port=")) {
                port = Integer.parseInt(arg.substring("--port=".length()));
            } else if (arg.equals("--dry-run")) {
                dryRun = true;
            } else {
                throw new IllegalArgumentException("Unknown argument: " + arg);
            }
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid port: " + port);
        }

        System.out.println("port=" + port);
        System.out.println("dryRun=" + dryRun);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ApplicationArgsDemo.java
java -Ddemo.port=9000 ApplicationArgsDemo --port=8081 --dry-run
~~~

**Stdout chính xác:**

~~~text
port=8081
dryRun=true
~~~

Cấu hình **9000** từ system property đã được đọc trước, nhưng đối số ứng dụng **--port=8081** ghi đè theo logic **for** do tác giả ứng dụng cài đặt. Đây là **quy tắc của ví dụ**, không phải quy luật ưu tiên bắt buộc trong Java SE.

Thử bỏ đối số port:

~~~bash
java -Ddemo.port=9000 ApplicationArgsDemo --dry-run
~~~

**Stdout chính xác:**

~~~text
port=9000
dryRun=true
~~~

Nếu không truyền **-Ddemo.port** và không có **--port=...**, chương trình lấy **8080**. Trong ví dụ học tập, giá trị port không phải số sẽ ném **NumberFormatException**; đối số không biết hoặc port ngoài 1–65535 sẽ ném **IllegalArgumentException**. Ứng dụng thực tế thường bắt lỗi, hiển thị hướng dẫn sử dụng và kết thúc với mã lỗi phù hợp.

Một framework có thể dùng tên tham số hoặc thứ tự ưu tiên khác; ví dụ Spring Boot có cơ chế command-line properties riêng. Không được áp dụng thứ tự ưu tiên cấu hình của một framework cho mọi chương trình Java.

## 9. Vị trí, vòng đời và phạm vi ảnh hưởng

Dòng thời gian khái quát:

~~~text
Người dùng / script / IDE / container
          |
          v
Shell hoặc công cụ khởi chạy xây dựng các token
          |
          v
Java launcher phân tích options và xác định main class/JAR
          |
          +--> VM options: cấu hình JVM tại khởi động
          |
          +--> -D: khởi tạo system properties
          |
          v
JVM khởi tạo, tải/liên kết/khởi tạo lớp theo nhu cầu
          |
          v
Gọi public static void main(String[] args)
          |
          +--> System.getProperty(...) đọc bảng properties
          |
          +--> args chứa các token chương trình nhận
          |
          v
Ứng dụng phân tích args, khởi tạo thành phần và chạy nghiệp vụ
~~~

Cần hiểu đây là sơ đồ khái quát, không phải danh sách mọi giai đoạn JVM theo thứ tự tuyệt đối: launcher và JVM có nhiều công việc nội bộ, lớp có thể được nạp trước hoặc sau main tùy nhu cầu.

| Câu hỏi | JVM/launcher option | System property | Application argument |
| --- | --- | --- | --- |
| Được cung cấp lúc chạy ở đâu? | Trước đích main/JAR | Thường bằng **-D** trước đích main/JAR | Sau đích main/JAR |
| Thời điểm xử lý đầu tiên | Trước khi chương trình vào main | Khi VM khởi tạo property; ứng dụng có thể đọc về sau | Khi main/framework nhận và phân tích |
| Ai sở hữu ý nghĩa? | Java launcher/JVM cụ thể | JVM sở hữu bảng property; ứng dụng/thư viện quy định ý nghĩa key tùy biến | Ứng dụng/framework sở hữu cú pháp và hành vi |
| Có tự nằm trong **args**? | Không, nếu đặt đúng vị trí | Không, đối với **-D** đã xử lý trước đích main | Có |
| Có thể sửa khi chạy? | Phần lớn tùy chọn startup không sửa qua một system property | Có API **setProperty/clearProperty**, nhưng thành phần dùng nó không nhất thiết reload | Có thể thay đổi dữ liệu logic do ứng dụng tạo sau khi parse; mảng **args** ban đầu không được Java tự “cập nhật” |

### 9.1. System properties được dùng chung trong một JVM

Các thành phần trong cùng tiến trình thường truy cập cùng bảng system properties. Nếu thư viện A gọi **System.setProperty("demo.profile", "test")**, mã B đọc bằng **System.getProperty(...)** về sau có thể thấy giá trị mới. Cách dùng property tùy tiện để lưu trạng thái nghiệp vụ động có thể tạo phụ thuộc ngầm và tình trạng tranh chấp giữa các thư viện/test.

Trong trường hợp ứng dụng có nhiều thread, việc đọc/ghi property phải được đánh giá theo tính nhất quán và cách thư viện tiêu thụ cấu hình; ngay cả khi bản thân thao tác bảng properties được đồng bộ an toàn, **cấu hình ứng dụng nhiều trường** không tự trở thành một giao dịch nguyên tử.

### 9.2. JVM options thường thuộc về một tiến trình cụ thể

Một máy có thể chạy nhiều tiến trình Java, mỗi tiến trình có options, properties và args riêng. Truyền **-Xmx512m** cho tiến trình A không tự thay đổi heap của B. Việc đặt **-Dapp.mode=dev** trong lệnh khởi chạy một chương trình cũng không biến nó thành system property của các tiến trình Java khác.

Ví dụ, lệnh **java** chạy ứng dụng do Gradle gọi có thể thuộc một tiến trình khác với **Gradle daemon**. Đặt **-Ddemo.profile=dev** trên lệnh gọi Gradle không mặc nhiên bảo đảm một tác vụ **JavaExec** hay ứng dụng được fork sẽ kế thừa property đó; cần cấu hình đúng nơi công cụ tạo tiến trình con cho phép.

## 10. Cách quan sát và chẩn đoán

### 10.1. Quan sát runtime và system properties

Trong mã Java:

~~~java
// Mã minh họa đặt trong một phương thức:
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("demo.profile", "(unset)"));
~~~

**java.version** phản ánh runtime đang thực thi. **demo.profile** phản ánh giá trị system property tại lúc gọi. Không có một output cố định cho **java.version** trên mọi máy.

Từ command line, công cụ **java -version** cho biết phiên bản/runtime nhưng không thay cho thử nghiệm chạy ứng dụng. Với HotSpot/JDK hỗ trợ, bạn có thể dùng các lệnh chẩn đoán:

~~~bash
java -XshowSettings:properties -version
java -XX:+PrintFlagsFinal -version
~~~

Đầu ra dài, phụ thuộc JDK và triển khai, thường gồm cả thông báo ở **stderr**. Đừng coi toàn bộ output của hai lệnh trên là ổn định giữa các phiên bản. Công cụ **jcmd** khi có quyền truy cập và được runtime hỗ trợ còn có các lệnh như **VM.command_line** hoặc **VM.system_properties** để điều tra một JVM đang chạy; danh sách lệnh khả dụng tùy JVM.

Trong chương trình, **ManagementFactory.getRuntimeMXBean().getInputArguments()** có thể cung cấp các đối số khởi chạy JVM do runtime ghi nhận, nhưng **không phải** API khôi phục nguyên dòng lệnh shell hoặc **String[] args** của ứng dụng. Đừng dùng nó thay parser CLI.

### 10.2. Các hiện tượng và hướng xử lý

| Triệu chứng | Kiểm tra đầu tiên | Cách xử lý |
| --- | --- | --- |
| Property trả về **null** hoặc mặc định | **-Dkey=value** có nằm trước tên main hoặc **-jar app.jar** không? Tên khóa có đúng chữ hoa/thường không? | Đặt **-D** đúng vị trí, dùng đúng tên và kiểm tra nguồn cấu hình |
| **args** chứa **-Xmx512m** hoặc **-D...** ngoài ý muốn | Tùy chọn có bị đặt phía sau main/JAR không? | Chuyển lên trước đích khởi chạy |
| JVM không khởi động vì cờ không hỗ trợ | Phiên bản và nhà cung cấp JDK có chấp nhận **-X/-XX** đó không? | Tham khảo tài liệu VM đang sử dụng; bỏ/thay cờ không tương thích |
| Đặt property mà heap không đổi | Có nhầm **-D...** với **-Xmx...** không? | Đặt VM option tương ứng trước main/JAR |
| Ứng dụng báo **Unknown argument** | Tham số có thuộc cú pháp riêng của ứng dụng không? | Đọc CLI help/contract của ứng dụng; sửa tên và vị trí |
| Property đúng nhưng thư viện vẫn dùng giá trị cũ | Thư viện có cache cấu hình ngay khi khởi tạo không? | Cấp giá trị sớm, hoặc dùng cơ chế reload chính thức nếu có |
| Chạy IDE đúng nhưng terminal sai | VM options, program arguments, environment variables có được nhập vào cùng vị trí không? | So sánh cấu hình chạy thực tế và working directory |
| Các tham số có khoảng trắng bị tách | Shell đã xử lý quoting như thế nào? | Quote phù hợp shell đích; xác minh **args** thực nhận |
| Đổi giá trị trong Gradle nhưng app fork không nhận | Đang cấu hình JVM của Gradle hay JVM ứng dụng? | Truyền VM options/properties/args trên đúng tác vụ và tiến trình |

### 10.3. Cẩn thận với dữ liệu nhạy cảm

Không nên đưa mật khẩu, token hay khóa bí mật vào command line hoặc system properties rồi in/log lại bừa bãi. Tham số dòng lệnh và một số system properties có thể được hiển thị bởi công cụ quản trị, thông tin tiến trình, báo lỗi hoặc chẩn đoán tùy môi trường. Hãy dùng cơ chế quản lý secret phù hợp và kiểm soát việc ghi log.

## 11. Bài tập tự thực hành

Dùng lớp **ConfigLayersDemo** ở mục 6 và dự đoán trước kết quả. Các câu hỏi dưới đây giả định không có biến môi trường hoặc công cụ khác chèn sẵn những demo properties.

**Bài 1.**

~~~bash
java -Ddemo.profile=test ConfigLayersDemo alpha beta
~~~

Câu hỏi: **profile**, **retries**, **argCount** và các phần tử **args** là gì?

**Đáp án:**

~~~text
profile=test
retries=(unset)
argCount=2
arg[0]=alpha
arg[1]=beta
~~~

**Bài 2.**

~~~bash
java ConfigLayersDemo --profile=test
~~~

Câu hỏi: Có system property **demo.profile=test** không?

**Đáp án:** Không tự có. **--profile=test** là **args[0]**; ví dụ chỉ in chuỗi này. Muốn application hiểu nó, phải viết parser CLI hoặc dùng framework tương ứng.

**Bài 3.**

~~~bash
java -Xmx256m ConfigLayersDemo --dry-run
~~~

Câu hỏi: Có cách nào đọc **-Xmx256m** bằng **args[0]** không?

**Đáp án:** Không trong lệnh này; **args[0]** là **--dry-run**. **-Xmx256m** đã được JVM tiêu thụ trước main. Muốn khảo sát giới hạn heap có thể dùng API theo hợp đồng runtime như **Runtime.getRuntime().maxMemory()**, nhưng không giả định con số phải đúng từng byte bằng giá trị viết trên dòng lệnh.

**Bài 4.** So sánh:

~~~bash
java -Ddemo.profile=dev ConfigLayersDemo
java ConfigLayersDemo -Ddemo.profile=dev
~~~

**Đáp án:** Lệnh đầu tạo system property và không truyền đối số ứng dụng; lệnh thứ hai không tạo property đó từ **-D** mà truyền nguyên token vào **args[0]**. Vị trí quyết định vai trò.

**Bài 5.** Trong **ApplicationArgsDemo**, tại sao **--port=8081** thắng **-Ddemo.port=9000**?

**Đáp án:** Code đọc system property làm giá trị ban đầu rồi duyệt **args** và gán lại biến **port**. Đổi thứ tự xử lý trong code có thể tạo quy tắc khác; JVM không áp đặt thứ tự ưu tiên ứng dụng.

## 12. Checklist khi triển khai

1. Xác định **ai** cần tham số: VM/launcher, hệ thống property, hay logic của ứng dụng.
2. Chọn **đúng cú pháp và vị trí**: options trước main/JAR; app args sau main/JAR.
3. Xác định phiên bản/JVM hỗ trợ các cờ **-X/-XX**, tránh áp dụng cờ không được hỗ trợ.
4. Với property do bạn tạo, đặt tên rõ ràng, chuyển kiểu/kiểm tra dữ liệu, mô tả mặc định và phạm vi thay đổi.
5. Với CLI args, định nghĩa parser, thông báo lỗi, help và quy tắc độ ưu tiên với các nguồn cấu hình khác.
6. Xác minh shell/IDE/build tool/container truyền **đúng token** vào **đúng tiến trình Java**.
7. Kiểm tra vận hành thực tế trên JVM mục tiêu; tránh log thông tin nhạy cảm.

**Ghi nhớ:** **-Xmx** thay đổi cấu hình VM; **-Dkey=value** là tùy chọn khởi động dùng để đặt **system property**, đọc bằng **System.getProperty(key)**; còn các token sau tên lớp main hoặc **-jar app.jar** đi vào **String[] args** và chỉ có nghĩa khi ứng dụng diễn giải chúng. Ba lớp này liên quan trong cùng một dòng lệnh nhưng không thể hoán đổi cho nhau.
