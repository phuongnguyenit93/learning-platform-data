# Nhận Instrumentation từ JVM và giữ tham chiếu trong suốt vòng đời Java agent

Khi khởi động ứng dụng với **-javaagent**, Java Virtual Machine (JVM) tải một lớp agent và gọi **premain** trước khi gọi **main** của ứng dụng. Tại điểm này, JVM **truyền trực tiếp một đối tượng java.lang.instrument.Instrumentation** cho agent. Đây là đầu mối để agent đăng ký **ClassFileTransformer**, xem những lớp đã nạp, kiểm tra khả năng biến đổi lớp và thực hiện các thao tác instrumentation được JVM hỗ trợ.

Vấn đề thực tế: tham số **Instrumentation** chỉ xuất hiện trong chữ ký callback khởi động, trong khi agent có thể cần sử dụng nó **sau khi premain đã trả về**. Vì vậy cần nhận đúng tham số, công bố tham chiếu an toàn, đặt nó ở vị trí có vòng đời phù hợp, bảo đảm các thành phần cùng nhìn thấy đúng một holder và kiểm soát các thao tác suốt thời gian agent hoạt động.

## 1. Kết quả cần đạt

Hoàn thành bài học này, bạn cần:

1. Viết được **public static void premain(String agentArgs, Instrumentation inst)** và giải thích khi nào JVM gọi nó.
2. Đóng gói đúng **agent JAR** với thuộc tính manifest **Premain-Class** và chạy ứng dụng bằng **-javaagent**.
3. Lưu **Instrumentation** vào một thành phần runtime dùng chung mà không phải tự tạo implementation của interface này.
4. Giải thích tại sao **static volatile**, tính an toàn khi công bố trạng thái, thứ tự khởi tạo và **class loader identity** quan trọng khi nhiều thành phần truy cập holder.
5. Sử dụng lại handle sau khi **premain** kết thúc; biết kiểm tra capability trước thao tác tùy chọn.
6. Xử lý trường hợp agent chưa được cài, cài lặp, nhiều agent cùng chạy, lỗi khởi động và dọn resource khi tắt.

Phạm vi của bài là **startup agent** qua **-javaagent**. Cơ chế nạp agent vào JVM đang chạy dùng **agentmain** là một entry point khác; không dùng nó để thay thế callback **premain** trong ví dụ này.

## 2. JVM cấp Instrumentation khi nào?

### 2.1. Trình tự khởi động

~~~text
Người dùng chạy:
  java -javaagent:my-agent.jar=options -cp ... com.example.Main
                │
                ▼
JVM khởi tạo phần runtime cần thiết
                │
                ▼
JVM đọc META-INF/MANIFEST.MF trong my-agent.jar
                │ tìm thuộc tính Premain-Class
                ▼
JVM tải lớp agent và gọi:
  public static void premain(String agentArgs, Instrumentation inst)
                │
                ├── nhận inst từ JVM
                ├── lưu tham chiếu vào holder
                ├── tùy nhu cầu: đăng ký transformer/khởi động dịch vụ
                ▼
premain trả về
                │
                ▼
JVM gọi main(String[] args) của ứng dụng
                │
                ▼
Agent tiếp tục phục vụ các callback và tác vụ đã đăng ký
~~~

Các lớp phục vụ việc khởi động JVM/agent vẫn có thể đã được tải **trước** khi agent được đăng ký. **premain trước main** không có nghĩa transformer nhìn thấy mọi lớp của JDK hoặc mọi lớp được load trước thời điểm đăng ký.

Trong triển khai hỗ trợ tùy chọn dòng lệnh, JVM có thể nhận **nhiều** đối số **-javaagent**. Các hàm **premain** của chúng được gọi theo thứ tự khai báo trên command line. Mỗi agent nên quản lý trạng thái của chính mình; đừng giả định tất cả agent đều là một lớp hoặc dùng chung một static field.

### 2.2. Hai chữ ký premain hợp lệ

~~~java
// Dạng ưu tiên khi agent cần Instrumentation:
public static void premain(String agentArgs, Instrumentation inst)

// Dạng tương thích nếu không cần tham số Instrumentation:
public static void premain(String agentArgs)
~~~

JVM thử tìm chữ ký **hai tham số** trước; nếu không có thì thử chữ ký **một tham số**. Đây là đoạn minh họa chữ ký, không phải file Java độc lập.

- **agentArgs** là **một chuỗi** tùy chọn, nhận từ phần sau dấu **=** trong **-javaagent:agent.jar=...**. Agent tự quyết định định dạng/việc parse; đó không phải **String[]** giống tham số của **main**.
- **inst** là đối tượng **Instrumentation do JVM cung cấp**. Interface này thuộc module **java.instrument**. Không tự khởi tạo bằng **new Instrumentation()**, không tạo bản giả thay thế JVM và không truy xuất nó bằng cách gọi một phương thức static giả định nào đó.
- Cả **premain** lẫn lớp agent phải được cấu hình hợp lệ. Nếu JVM không tìm được lớp hoặc chữ ký hợp lệ, hay **premain** ném ngoại lệ không được bắt, JVM có thể **hủy khởi động trước khi main chạy**.

Đối tượng được truyền chính là nguồn quyền năng instrumentation của JVM hiện tại. Theo tài liệu API, sau khi có tham chiếu, agent có thể gọi những phương thức được hỗ trợ trên nó ở các thời điểm về sau; **premain không cần giữ mã lệnh đang chạy** để handle còn dùng được.

## 3. Vì sao phải giữ tham chiếu, và nên đặt ở đâu?

Đoạn code sau có vấn đề về khả năng sử dụng lâu dài:

~~~java
// Minh họa thiếu cơ chế chia sẻ; không phải một lớp chạy độc lập.
public static void premain(String args, Instrumentation instrumentation) {
    System.out.println(instrumentation.getAllLoadedClasses().length);
}
// Một service khác không có đường truy cập trực tiếp tới tham số cục bộ ở trên.
~~~

Tham số phương thức chỉ truy cập trực tiếp được trong phạm vi callback. Khi **premain** trả về, một service xử lý lệnh hoặc bộ phận quản lý transformer vẫn cần cách lấy cùng handle. Đường tổ chức đơn giản cho **một agent trong một JVM** là:

~~~text
BootAgent.premain(..., Instrumentation từ JVM)
                     │
                     ▼
AgentRuntime.install(instrumentation)
                     │ công bố tham chiếu một lần
                     ▼
AgentRuntime.required()
          │
          ├── TransformerCoordinator
          ├── DiagnosticsService
          └── AgentLifecycle
~~~

Đây là **một holder agent-owned**, thay vì phân phát tham chiếu qua biến cục bộ hoặc truyền vào mọi đối tượng không cần biết tới JVM instrumentation.

Lợi ích:

- Có **một điểm nhận** và **một điều kiện sẵn sàng** rõ ràng.
- Mỗi consumer lấy handle thông qua phương thức có kiểm tra, nên lỗi “chưa khởi động bằng agent” xuất hiện sớm và dễ hiểu.
- Không cần cài đặt lại interface **Instrumentation** hoặc phụ thuộc vào API nội bộ của JVM.
- Có thể tách mã khởi động ngắn gọn khỏi các dịch vụ khác của agent; sau này có thể bọc quyền hạn qua một service hẹp hơn.

**Static field là lựa chọn đơn giản, không phải phép màu JVM-wide**: static thuộc về một **Class** cụ thể do một **class loader** định nghĩa. Nếu hai loader tạo hai bản **AgentRuntime**, mỗi bản có static state riêng. Phần đóng gói và nhận diện loader ở dưới rất quan trọng.

## 4. Ví dụ hoàn chỉnh: nhận, lưu và dùng lại Instrumentation

Ví dụ dùng **Java 17+**, không cần thư viện bên ngoài. Để dễ chạy, ba lớp nằm trong **default package**; dự án thực tế nên đặt trong package của agent và đóng gói nhất quán.

### 4.1. File AgentRuntime.java — holder có bảo vệ

~~~java
// File: AgentRuntime.java
import java.lang.instrument.Instrumentation;
import java.util.Objects;

public final class AgentRuntime {
    private static volatile Instrumentation instrumentation;

    private AgentRuntime() {
        // Không tạo instance của holder.
    }

    static synchronized void install(Instrumentation supplied) {
        Objects.requireNonNull(supplied, "instrumentation");

        if (instrumentation != null) {
            if (instrumentation == supplied) {
                return; // cùng handle: an toàn nếu được gọi lại có chủ đích
            }
            throw new IllegalStateException(
                    "A different Instrumentation was already installed"
            );
        }

        instrumentation = supplied;
    }

    public static boolean isInstalled() {
        return instrumentation != null;
    }

    public static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Agent was not initialized through premain"
            );
        }
        return current;
    }
}
~~~

Cách thiết kế hoạt động:

- **private static volatile Instrumentation**: giữ một tham chiếu chung cho đúng lớp **AgentRuntime**; **volatile** tạo bảo đảm visibility/happens-before khi **premain** ghi và các luồng khác đọc sau đó.
- **synchronized install(...)**: tránh cạnh tranh khi có nhiều lời gọi cài đặt. Cách này cố ý không cho thay một handle đã lưu bằng một handle khác. Trong luồng startup thông thường, JVM gọi **premain** một lần cho lượt khởi động agent; kiểm tra cài lặp là hàng rào phòng lỗi thiết kế hoặc lời gọi ngoài ý muốn.
- **Objects.requireNonNull(...)**: phát hiện ngay trường hợp caller truyền giá trị không hợp lệ.
- **required()**: đọc volatile **một lần** vào biến local; nếu chưa sẵn sàng thì ném exception có ngữ nghĩa rõ ràng. Nó trả về đúng đối tượng đã được cài, không tạo instance mới.
- **install** để package-private: trong mẫu một package, code ứng dụng không được khuyến khích tự gán handle. Với production, có thể đưa API này vào package nội bộ và chỉ cung cấp các nghiệp vụ được phép thay vì trả raw handle cho tất cả thành phần.

Không dùng **final** trực tiếp cho trường hợp khởi tạo sau khi class được load, bởi JVM chỉ truyền giá trị khi callback **premain** thực thi. Không dùng **ThreadLocal** để giữ handle vì các luồng khác sẽ không cùng nhìn thấy giá trị; không dùng **WeakReference** vì không có lý do buộc việc truy cập API của agent phụ thuộc garbage collector.

### 4.2. File BootAgent.java — entry point của JVM

~~~java
// File: BootAgent.java
import java.lang.instrument.Instrumentation;

public final class BootAgent {
    private BootAgent() {
    }

    public static void premain(String agentArgs,
                               Instrumentation instrumentation) {
        AgentRuntime.install(instrumentation);

        System.out.println("premain: args=" + agentArgs);
        System.out.println(
                "premain: installed=" + AgentRuntime.isInstalled()
        );

        // Sau khi lưu handle, có thể đăng ký transformer hoặc khởi
        // tạo các dịch vụ của agent nếu thực sự cần.
    }
}
~~~

Điểm cốt lõi là gọi **AgentRuntime.install(instrumentation)** trước khi tạo thread phụ, đăng ký callback hoặc công bố service có thể truy cập holder. Trong trường hợp sử dụng một số transformer hoặc service phức tạp, việc đăng ký có thể làm JVM tải lớp bổ sung; vì vậy thứ tự công bố trạng thái và giảm tải công việc trong **premain** giúp tránh lỗi khởi tạo lồng nhau.

### 4.3. File ExampleApplication.java — kiểm chứng sau premain

~~~java
// File: ExampleApplication.java
public final class ExampleApplication {
    public static void main(String[] args) {
        System.out.println(
                "main: installed=" + AgentRuntime.isInstalled()
        );

        int loaded = AgentRuntime.required()
                                 .getAllLoadedClasses()
                                 .length;
        System.out.println("main: hasLoadedClasses=" + (loaded > 0));
    }
}
~~~

Ở ví dụ này, **main** kiểm tra holder và gọi **getAllLoadedClasses()** để chứng minh handle vẫn sử dụng được sau khi **premain** kết thúc. Kết quả chỉ kiểm tra xem JVM có ít nhất một lớp đã được tải; tổng số lớp phụ thuộc JDK và tiến trình nên không cố định.

### 4.4. File agent.mf — manifest của agent JAR

Tạo một file văn bản **agent.mf** chứa:

~~~text
Manifest-Version: 1.0
Premain-Class: BootAgent
~~~

Phải có **newline ở cuối file manifest** để thuộc tính cuối được ghi nhận đúng theo định dạng. **Premain-Class** là **tên nhị phân của lớp**, không phải đường dẫn **BootAgent.class** hay tên file Java. Nếu dùng package, chẳng hạn **org.example.agent.BootAgent**, giá trị manifest phải chứa đầy đủ tên có dấu chấm.

### 4.5. Biên dịch, đóng JAR và chạy

Đặt bốn file **AgentRuntime.java**, **BootAgent.java**, **ExampleApplication.java**, **agent.mf** vào cùng một thư mục rồi chạy:

~~~bash
javac --release 17 AgentRuntime.java BootAgent.java ExampleApplication.java
jar cfm boot-agent.jar agent.mf BootAgent.class AgentRuntime.class
java -javaagent:boot-agent.jar=inspect -cp . ExampleApplication
~~~

Output trên một JVM Java 17 hỗ trợ Java agent:

~~~text
premain: args=inspect
premain: installed=true
main: installed=true
main: hasLoadedClasses=true
~~~

Giải thích tuần tự:

1. **javac** tạo class file tương thích Java 17. Hai file **BootAgent.class** và **AgentRuntime.class** được đóng vào agent JAR; **ExampleApplication.class** ở classpath của ứng dụng.
2. **jar cfm** tạo JAR với manifest từ **agent.mf**. JVM đọc **Premain-Class: BootAgent** và tìm **BootAgent.premain(String, Instrumentation)**.
3. Phần **=inspect** được truyền nguyên chuỗi **inspect** vào **agentArgs**. Nó không tự trở thành đối số cho **ExampleApplication.main**.
4. **premain** lưu **Instrumentation** và in hai dòng đầu, rồi trả về. **main** lấy lại handle từ **AgentRuntime.required()**, in hai dòng sau.
5. Agent JAR được đưa vào đường tìm lớp của system class loader trong cơ chế startup agent thông thường. Trong ví dụ này **BootAgent**, **AgentRuntime** và **ExampleApplication** được tìm bởi cùng system/application class loader, nên **main** nhìn đúng static field mà **premain** đã gán.

Thử chạy **không** thêm **-javaagent**:

~~~bash
java -cp . ExampleApplication
~~~

**main** sẽ in **main: installed=false**, sau đó **AgentRuntime.required()** ném **IllegalStateException** với thông báo **Agent was not initialized through premain**. Đây là lỗi có chủ đích, giúp tránh diễn giải nhầm rằng Instrumentation tự xuất hiện trong ứng dụng Java bình thường; phần stack trace phụ thuộc JVM nên không liệt kê một output cố định.

> **Điều kiện đóng gói quan trọng:** nếu ứng dụng thật và agent dùng nhiều class loader hoặc module khác nhau, hãy xác định một API chia sẻ rõ ràng, bảo đảm holder được resolve về đúng **Class**. Một lớp cùng tên được định nghĩa lại ở loader khác không chia sẻ static field. Không nên sao chép **AgentRuntime.class** vào nhiều loader rồi trông chờ các bản copy tự chia sẻ trạng thái.

## 5. Vòng đời của tham chiếu và vòng đời công việc của agent

**Giữ Instrumentation** chỉ là giữ **khả năng gọi API**. Nó không đồng nghĩa JVM sẽ tự đăng ký transformer, tự khởi tạo scheduler hoặc tự quan sát mọi sự kiện cho bạn.

| Thời điểm | Trạng thái của handle | Việc agent thường thực hiện |
| --- | --- | --- |
| Trước khi JVM gọi premain | Holder chưa có giá trị | Consumer không được giả định **required()** thành công |
| Trong premain | JVM truyền **inst**; holder được gán | Kiểm tra cấu hình, thiết lập transformer và resource cần thiết |
| Sau khi premain trả về | Holder vẫn giữ tham chiếu static | Callback hoặc service dùng lại handle cho các tác vụ được phép |
| Trong lúc ứng dụng chạy | Nhiều thread có thể đọc cùng handle | Đồng bộ hóa state của agent; tránh đăng ký lặp hoặc thao tác gây race |
| Khi agent ngừng hoạt động | Handle có thể vẫn nằm trong holder | Hủy đăng ký transformer thích hợp, đóng resource do agent sở hữu |
| Khi JVM kết thúc | Đối tượng Instrumentation thuộc JVM này không còn ý nghĩa | Lượt chạy JVM tiếp theo nhận một đối tượng/callback mới |

**Instrumentation không có phương thức close().** Vì vậy một agent muốn ngừng quan sát cần dừng **những hoạt động đã đăng ký hoặc đã tạo**: remove transformer, dừng background service, đóng file/socket hoặc executor do agent sở hữu. Không có một lệnh chung “đóng Instrumentation” để tự động thu hồi tất cả side effect.

**Không serialize hoặc lưu tham chiếu sang JVM khác**: đây là một API runtime gắn với tiến trình và môi trường JVM hiện tại, không phải token hay cấu hình có thể lưu xuống disk. Sau khi JVM thoát, mọi state của holder mất đi theo tiến trình.

### 5.1. Có cần giữ strong reference không?

Một static field thông thường giữ **strong reference** đến **Instrumentation** trong vòng đời của lớp chứa nó. Đây là cách hợp lý nếu agent cần dùng lại lâu dài. Tuy nhiên, đừng biến holder thành kho giữ mọi **Class**, **ClassLoader**, transformer hoặc object của ứng dụng: các cache strong reference không có chiến lược thu hồi có thể ngăn class loader và plugin cũ được giải phóng.

Giữ handle ổn định không có nghĩa giữ mọi đối tượng liên quan vĩnh viễn. Hãy quản lý riêng vòng đời của resource bổ sung.

### 5.2. Có được thay Instrumentation tại runtime không?

Trong phạm vi startup agent thông thường, không cần một cơ chế **setInstrumentation(...)** công khai cho mọi caller, cũng không cần việc “refresh” handle theo thời gian. Việc gán lại tùy tiện sẽ làm mất bảo đảm của các service giữ tham chiếu trước đó. Chính sách cài một lần và cho phép gọi lại với **cùng tham chiếu** của ví dụ là lựa chọn đơn giản, dễ kiểm soát.

Nếu ứng dụng hỗ trợ nhiều hình thức nạp agent, phải định nghĩa rõ ai sở hữu initialization và state trước khi ghép các entry point lại; không suy luận rằng callback về sau được phép thay giá trị đã cài.

## 6. Safe publication và xử lý đồng thời

### 6.1. Tại sao volatile quan trọng?

Hãy hình dung:

~~~text
Luồng khởi động (premain)          Luồng xử lý sự kiện (agent)
         │                                  │
         ├── install(inst)                   │
         │    volatile write                │
         │                                  ├── required()
         │                                  │    volatile read
         │                                  └── nhận đúng tham chiếu
         ▼
       trả về
~~~

Trong Java Memory Model, **volatile write** happens-before những volatile read tiếp theo trên cùng biến trong thứ tự đồng bộ tương ứng. Vì vậy consumer đọc được tham chiếu đã công bố đúng cách. Việc khởi tạo cấu hình khác có thể cần quan hệ happens-before riêng; **volatile không khiến mọi cấu trúc dữ liệu mutable của agent trở nên thread-safe**.

Đối với ví dụ đơn giản, **premain** hoàn tất trước khi JVM gọi ứng dụng **main**, nhưng agent thật có thể tạo worker thread hoặc callback ngay trong giai đoạn khởi động. **volatile** làm hợp đồng công bố trạng thái rõ ràng cho những consumer đa luồng này.

### 6.2. Đồng bộ hóa cài đặt khác với đồng bộ hóa sử dụng

**synchronized install(...)** chỉ bảo vệ bước quyết định có được gán lần đầu hay không. Nó **không** khiến các thao tác trên transformer, cache, counters hay resource khác đồng bộ với nhau. Khi nhiều thread:

- Đăng ký/loại bỏ transformer, hãy quản lý identity và thứ tự thực hiện.
- Ghi metric, dùng atomic/LongAdder hoặc cơ chế phù hợp thay vì **int++** không được bảo vệ.
- Chia sẻ map/cache, dùng cấu trúc thread-safe và bảo vệ các thao tác nhiều bước khi cần.
- Khởi chạy/đóng service, xác định rõ trạng thái **STARTING**, **RUNNING**, **STOPPING**, **STOPPED** nếu workflow phức tạp.

Ví dụ holder dùng **volatile + synchronized** là đủ để **công bố một handle duy nhất**. Đừng tự động mở rộng cùng cơ chế sang mọi state mà không xem tính nguyên tử và quy tắc vòng đời của từng tài nguyên.

## 7. Dùng handle sau premain: thao tác nào được hỗ trợ?

Sau khi **AgentRuntime.required()** trả về handle, các service có thể dùng API **Instrumentation**. Tuy nhiên, mỗi phương thức có hợp đồng riêng:

| Nhóm thao tác | API tiêu biểu | Điều phải hiểu |
| --- | --- | --- |
| Quan sát lớp | **getAllLoadedClasses()**, **getInitiatedClasses(loader)** | Kết quả chỉ phản ánh tình trạng tại thời điểm truy vấn; không cố định |
| Đăng ký bytecode transform | **addTransformer(transformer)** | Áp dụng cho những lần định nghĩa phù hợp trong tương lai; không tự sửa lớp cũ |
| Gỡ transformer | **removeTransformer(transformer)** | Cần đúng instance đã đăng ký; callback đang diễn ra có thể tiếp tục sau khi gỡ |
| Retransform lớp cũ | **isRetransformClassesSupported()**, **retransformClasses(...)** | Khả năng tùy chọn; kiểm tra manifest, JVM và lớp đích |
| Redefine lớp cũ | **isRedefineClassesSupported()**, **redefineClasses(...)** | Khả năng tùy chọn; giới hạn thay đổi định nghĩa đang tồn tại |
| Kiểm tra lớp | **isModifiableClass(clazz)** | Trả **true** chưa đủ: thao tác còn cần capability phù hợp |
| Thống kê kích thước | **getObjectSize(object)** | Giá trị xấp xỉ theo implementation, không phải deep size của object graph |
| Điều chỉnh module | **redefineModule(...)** | Mở rộng reads/exports/opens theo điều kiện API; không cho phép tùy tiện phá mọi giới hạn JVM |

### 7.1. Một đoạn consumer nhỏ

Đây là **đoạn minh họa cho service đã ở cùng class loader với holder**, không phải chương trình chạy độc lập:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

final class AgentTransformerService {
    private final ClassFileTransformer transformer;

    AgentTransformerService(ClassFileTransformer transformer) {
        this.transformer = transformer;
    }

    void start() {
        Instrumentation inst = AgentRuntime.required();
        inst.addTransformer(transformer, false);
    }

    void stop() {
        Instrumentation inst = AgentRuntime.required();
        inst.removeTransformer(transformer);
    }
}
~~~

Trong production cần quản lý **start/stop idempotent** và trạng thái đăng ký, tránh gọi **addTransformer** nhiều lần với cùng instance. API cho phép nhiều đăng ký nhưng không nên dựa vào đó. **removeTransformer** loại bỏ một đăng ký phù hợp, không bảo đảm mọi callback đang chạy đã kết thúc tức thì. Một transformer phải được viết sao cho việc callback diễn ra đồng thời với shutdown không làm hỏng state.

Nếu agent chỉ cần quan sát lớp mới, lời gọi **addTransformer(transformer)** mặc định tương đương **addTransformer(transformer, false)**; không cần khai báo capability retransform.

### 7.2. Khả năng tùy chọn phụ thuộc manifest và JVM

Ngoài **Premain-Class**, manifest có thể khai báo:

~~~text
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Đây là **hai thuộc tính minh họa, không nằm trong manifest tối thiểu của ví dụ**. Mặc định chúng là **false** nếu không khai báo. Khai báo **true** chỉ có nghĩa agent yêu cầu capability; JVM vẫn phải hỗ trợ. Do đó vẫn phải kiểm tra **isRetransformClassesSupported()** hoặc **isRedefineClassesSupported()**, và kiểm tra **isModifiableClass(clazz)** trước khi định thử thao tác với một lớp cụ thể.

Một kiểm tra an toàn bằng code:

~~~java
// Đoạn minh họa bên trong service, với biến target là một Class<?> hợp lệ.
Instrumentation inst = AgentRuntime.required();
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    // Lúc này có thể cân nhắc inst.retransformClasses(target),
    // sau khi đảm bảo transformer và bytecode đáp ứng giới hạn JVM.
}
~~~

Không có quyền/capability thì **đừng** gọi thẳng **retransformClasses(...)** rồi hy vọng mọi JVM đều chấp nhận. Khi retransform một lớp, JVM không chạy lại static initializer chỉ vì bạn cập nhật method bytecode.

## 8. Class loader và module: vì sao static holder có thể “biến mất”?

Một lỗi dễ gây khó hiểu là agent đã in **installed=true**, nhưng một thành phần khác đọc **AgentRuntime.isInstalled()** lại nhận **false**. Trường hợp này cần kiểm tra:

1. Consumer và agent có tham chiếu tới đúng **Class** mang tên **AgentRuntime** không?
2. **AgentRuntime.class.getClassLoader()** ở hai nơi có cùng defining loader không?
3. Có hai bản JAR chứa cùng FQCN trong những class loader độc lập không?
4. Consumer thuộc **named module** hay **unnamed module**? Package của holder có được nhìn thấy theo quy tắc truy cập và module readability phù hợp không?
5. Consumer có chạy **trước khi premain cài handle** hoặc chạy ở một JVM/process khác không?

Với startup agent qua **-javaagent**, các lớp trong agent JAR thông thường được nạp bằng **system class loader**, thuộc **unnamed module** của loader này. Điều đó không có nghĩa một ứng dụng chạy qua custom loader/plugin hoặc một named module tùy ý đều tự động truy cập mọi package của agent.

Ví dụ chẩn đoán có thể đặt vào phần phù hợp của cả agent và consumer:

~~~java
System.out.println(AgentRuntime.class.getClassLoader());
System.out.println(AgentRuntime.class.getModule());
~~~

Output chứa tên object/loader phụ thuộc runtime, vì vậy không có chuỗi stdout cố định ở đây. Nếu loader khác nhau, cần thiết kế lại **ranh giới API chia sẻ** (chẳng hạn một lớp bridge đặt ở loader được cả hai bên tham chiếu, interface công khai hợp lệ, hoặc truyền dependency từ agent vào service trong cùng loader). Không sửa bằng cách tùy tiện nhân bản class holder hay cưỡng ép reflection.

Khi không thật sự cần ứng dụng truy cập trực tiếp **Instrumentation**, nên giữ holder trong phần nội bộ của agent và đưa ra một API nghiệp vụ hẹp; ứng dụng thông thường không cần phụ thuộc vào agent runtime.

## 9. Thứ tự khởi tạo và cách xử lý lỗi khởi động

### 9.1. Thứ tự khuyến nghị trong premain

~~~text
1. Nhận/kiểm tra agentArgs và Instrumentation.
2. Cài handle vào holder.
3. Kiểm tra capability phù hợp với cấu hình.
4. Tạo state, transformer, dịch vụ cần thiết.
5. Đăng ký callback/transformer sau khi state đã sẵn sàng.
6. Trả về để JVM tiếp tục gọi main.
~~~

Thứ tự này có thể điều chỉnh theo thiết kế, nhưng nguyên tắc là **consumer không được chạy trước khi dependency của nó được công bố an toàn**. Nếu agent khởi chạy thread trong **premain**, hãy khởi tạo những dependency mà thread cần trước lúc **start()**. Nếu transformer có thể bị gọi trong quá trình định nghĩa các lớp dùng bởi chính agent, cần lọc lớp và hạn chế class loading tái nhập.

Không làm quá nhiều việc blocking trong **premain** nếu không cần: JVM chờ callback trả về trước khi thực thi **main**. Log cẩn thận để chẩn đoán, nhưng nếu lỗi thực sự khiến agent không an toàn thì throw có chủ đích thay vì bỏ qua và để ứng dụng khởi chạy trong trạng thái nửa vời. Ngược lại, lỗi của tính năng agent tùy chọn có thể được xử lý theo chính sách degrade được thiết kế rõ.

### 9.2. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| JVM không chạy tới main khi thêm **-javaagent** | Không đọc được agent JAR, thiếu **Premain-Class**, sai tên class hoặc chữ ký **premain**, exception chưa bắt | Xem manifest, tên package, method **public static**, stack trace đầu tiên |
| **premain** nhận được args sai kỳ vọng | Nhầm **agentArgs** với **String[] args** của main; sai phần **=options** | In chuỗi agentArgs và tự parse định dạng đã thiết kế |
| **AgentRuntime.required()** ném **IllegalStateException** | Chạy ứng dụng thiếu **-javaagent** hoặc truy cập quá sớm | Xác nhận launch command và thứ tự initialize |
| Agent in đã cài nhưng consumer thấy trống | Nhiều bản **AgentRuntime** do các defining loader khác nhau hoặc JVM khác | So sánh **Class** object, loader, module và tiến trình |
| **NoClassDefFoundError** khi load agent | Quên đóng gói class phụ trợ/dependency vào agent JAR hoặc sai loader visibility | Kiểm tra danh sách file trong JAR và dependency |
| **UnsupportedOperationException** khi retransform | Agent/JVM không hỗ trợ capability cần thiết | Xem **Can-Retransform-Classes** và **isRetransformClassesSupported()** |
| Có callback sau khi **removeTransformer** | Callback đã được JVM kích hoạt trước khi gỡ, chạy đồng thời | Thiết kế shutdown an toàn; không xem remove là hàng rào chờ tất cả callback |
| Ứng dụng treo trong startup | Premain chờ lâu, deadlock loader/transformer hoặc thread giữ khóa | Thread dump, log có timestamp, khóa và luồng khởi tạo |

Có thể kiểm tra những file agent vừa đóng gói bằng:

~~~bash
jar tf boot-agent.jar
~~~

Bạn cần thấy tối thiểu **META-INF/MANIFEST.MF**, **BootAgent.class** và **AgentRuntime.class**. Tên file tồn tại chưa chứng minh manifest đúng: hãy đối chiếu chính xác nội dung **Premain-Class** trong main manifest và tên nhị phân của lớp thực.

### 9.3. Đừng nuốt lỗi làm mất tính nhất quán

Cần phân biệt:

- **Lỗi cấu hình/khởi tạo bắt buộc**: nếu không có Instrumentation hoặc cài nhầm instance, agent phụ thuộc handle không thể thực hiện chức năng cốt lõi. Báo lỗi rõ nguyên nhân.
- **Tính năng tùy chọn**: nếu hệ thống giám sát được thiết kế để chạy ngay cả khi không hỗ trợ retransform, có thể vô hiệu hóa tính năng ấy và ghi trạng thái. Không tuyên bố đã kích hoạt retransform khi kiểm tra capability thất bại.
- **Lỗi runtime sau khi khởi động**: handle vẫn tồn tại, nhưng transformer, service hay resource có thể không hoạt động. Cần quản lý trạng thái hoạt động riêng; **isInstalled() chỉ xác nhận tham chiếu đã được công bố**.

## 10. Ranh giới trách nhiệm và lưu ý thiết kế production

### 10.1. Holder không nên sở hữu mọi thứ

**AgentRuntime** có trách nhiệm hẹp: cài một lần và cung cấp handle. Các trách nhiệm khác nên có nơi riêng:

- **AgentBootstrap/BootAgent**: nhận callback **premain**, đọc cấu hình và điều phối khởi động.
- **TransformerCoordinator**: tạo, đăng ký, quản lý và gỡ các transformer theo lifecycle.
- **DiagnosticsService**: thực hiện truy vấn quan sát khi cần, giới hạn chi phí truy vấn.
- **AgentLifecycle**: quản lý executor, file/socket, hook và lệnh shutdown nếu agent tạo chúng.

Mô hình này khiến code kiểm soát Instrumentation dễ audit. Một method tĩnh trả raw **Instrumentation** có thể thích hợp với mã nội bộ nhỏ, nhưng nếu công bố cho plugin hoặc consumer tùy ý, hãy cân nhắc API chỉ cho phép các tác vụ mong muốn thay vì trao toàn bộ quyền biến đổi lớp của JVM.

### 10.2. Không đồng nhất “đã lưu” với “đã hoạt động”

Một cách đo readiness chi tiết hơn khi agent lớn có thể là:

~~~text
UNINITIALIZED
    │ premain nhận Instrumentation
    ▼
INITIALIZING
    │ cài holder, nạp cấu hình, đăng ký callback
    ▼
RUNNING
    │ yêu cầu dừng hoặc JVM shutdown
    ▼
STOPPING
    │ remove transformer, dừng executor và đóng resource
    ▼
STOPPED
~~~

Đây là **mô hình kiến trúc minh họa**, không phải trạng thái có sẵn của API **Instrumentation**. Holder chỉ biết handle có tồn tại hay không; trạng thái **RUNNING** cần một lifecycle manager của chính agent nếu tác vụ khởi động có thể thất bại từng phần.

Một agent tạo non-daemon thread có thể khiến tiến trình không thoát như mong muốn; quyết định daemon mode, shutdown hook và cleanup phải theo yêu cầu sản phẩm. Không tự xóa **Instrumentation** khỏi holder để mô phỏng shutdown nếu vẫn còn callback cần nó; hãy tắt những hoạt động đã sở hữu theo thứ tự an toàn.

## 11. Tự kiểm tra kiến thức

1. **Tại sao Java application không thể đơn giản new Instrumentation?** Vì đó là interface do cơ chế JVM instrumentation cung cấp; object hợp lệ được truyền qua agent entry point, không phải thành phần ứng dụng tự khởi tạo.
2. **Khi chạy -javaagent, JVM tìm phương thức nào trước?** **premain(String, Instrumentation)**; nếu không có thì mới thử **premain(String)**. Dùng dạng hai tham số để nhận handle.
3. **premain trả về rồi Instrumentation có hết hiệu lực không?** Không. Agent giữ tham chiếu và vẫn có thể gọi các API được hỗ trợ trong JVM hiện tại.
4. **Để một service trên thread khác thấy handle, static field có cần volatile không?** Có thể đạt safe publication bằng những cơ chế đồng bộ hóa khác; trong ví dụ, **volatile** là cách rõ ràng và đủ để công bố tham chiếu. Nó không tự đồng bộ hóa các cấu trúc dữ liệu khác.
5. **Hai lớp AgentRuntime trùng tên trong hai loader có chia sẻ static instrumentation không?** Không. Mỗi định nghĩa runtime của lớp có static storage riêng.
6. **isInstalled() trả true có nghĩa mọi class đều có thể retransform không?** Không. Phải kiểm tra capability JVM/manifest, khả năng sửa của từng lớp và giới hạn bytecode/schema.
7. **removeTransformer có đợi toàn bộ callback đang chạy kết thúc không?** Không có bảo đảm như vậy; callback có thể tiếp tục sau khi gỡ.
8. **Khi JVM thoát, có thể giữ Instrumentation và dùng cho lần chạy kế tiếp không?** Không. Tham chiếu gắn với runtime JVM cũ; lần chạy mới phải được khởi động và khởi tạo agent lại.

## 12. Checklist trước khi đưa startup agent vào hệ thống thật

- Manifest agent JAR có **Premain-Class** đúng tên nhị phân của lớp chứa **public static premain** hai tham số.
- JVM được chạy với **-javaagent:...**, và agentArgs được parse có chủ đích.
- **Instrumentation** chỉ được lấy từ tham số JVM và được cài vào holder trước khi consumer/callback sử dụng.
- Holder có quy tắc **single initialization**, safe publication và báo lỗi rõ khi chưa sẵn sàng.
- Agent và consumer cùng thấy đúng một **Class** của holder, hoặc có API chuyển tiếp hợp lệ qua ranh giới loader/module.
- Các capability tùy chọn được kiểm tra bằng **is...Supported()**; không cho rằng đặt manifest flag là đủ.
- Transformer và resource được quản lý theo lifecycle; **removeTransformer** không được giả định là khóa chờ callback.
- Sự kiện “đã có handle” và “agent RUNNING” được phân biệt; failure handling cho initialization và cleanup nhất quán.
- Chạy thử có và không có **-javaagent** để xác nhận đường khởi động và thông báo lỗi.

## 13. Tài liệu chính thức

- [JDK 17 — Package java.lang.instrument, Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JDK 17 — Instrumentation interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JDK 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java Language Specification 17 — Threads and Locks / Java Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)

Ví dụ sử dụng public API của Java 17, không cần preview feature. Sự hỗ trợ với retransform/redefine và nội dung log lỗi cụ thể phụ thuộc JVM và cấu hình chạy.
