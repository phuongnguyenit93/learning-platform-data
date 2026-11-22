# Virtual thread và structured concurrency: kiểm tra hỗ trợ theo bản dựng

Virtual thread và structured concurrency là hai cách tiếp cận quan trọng khi xây dựng ứng dụng Java có nhiều tác vụ đồng thời. Virtual thread giúp tạo và quản lý số lượng lớn tác vụ chạy đồng thời với chi phí thấp hơn platform thread trong nhiều workload. Structured concurrency tổ chức các tác vụ con theo phạm vi của tác vụ cha, giúp quản lý việc chờ kết quả, hủy tác vụ và xử lý lỗi theo một vòng đời rõ ràng.

Khi đưa hai tính năng này vào ứng dụng dùng CRaC, cần kiểm tra hỗ trợ theo đúng bản dựng JDK, Gradle toolchain, compiler, test runtime và runtime triển khai. Virtual threads đã trở thành tính năng chính thức từ Java 21. Structured concurrency được giới thiệu dưới dạng preview API và API có thể thay đổi giữa các bản JDK. Một bản dựng biên dịch thành công chưa đủ chứng minh ứng dụng có thể chạy trên runtime khác hoặc có thể checkpoint/restore an toàn.

## 1. Phân biệt virtual thread và structured concurrency

Hai khái niệm có liên quan nhưng giải quyết hai vấn đề khác nhau:

| Khái niệm | Giải quyết vấn đề | Vòng đời |
|---|---|---|
| Virtual thread | Cách chạy một tác vụ trên một thread nhẹ do JVM quản lý | Thread có thể được tạo, chạy, chờ và kết thúc như thread Java |
| Structured concurrency | Cách nhóm và điều phối các tác vụ con theo phạm vi của tác vụ cha | Tác vụ cha chờ hoặc hủy các tác vụ con trước khi rời phạm vi |

Virtual thread không tự tạo ra cấu trúc cha-con cho các tác vụ. Ngược lại, structured concurrency không đồng nghĩa mọi tác vụ con bắt buộc phải chạy bằng virtual thread; executor hoặc thread factory được dùng phụ thuộc API và cấu hình của bản JDK.

Khi sử dụng cùng nhau, ứng dụng có thể tạo một scope để khởi chạy nhiều tác vụ con, đồng thời cho từng tác vụ chạy trên virtual thread. Scope giúp đảm bảo tác vụ con được quản lý cùng với đơn vị công việc cha.

## 2. Virtual thread: trạng thái hỗ trợ và cách kiểm tra

Virtual thread được hoàn thiện trong Java 21 (JEP 444). Từ Java 21, ứng dụng có thể sử dụng API chính thức như:

- Thread.ofVirtual() để tạo Thread bằng virtual thread builder.
- Thread.startVirtualThread(...) để tạo và bắt đầu một virtual thread.
- Executors.newVirtualThreadPerTaskExecutor() để tạo executor chạy mỗi task bằng một virtual thread mới.
- Thread.currentThread().isVirtual() để nhận biết thread hiện tại là virtual thread hay platform thread.

Ví dụ dùng executor:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first = executor.submit(
                    () -> loadProfile("user-01"));
            Future<String> second = executor.submit(
                    () -> loadOrders("user-01"));

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }

    private static String loadProfile(String userId) {
        return "profile:" + userId;
    }

    private static String loadOrders(String userId) {
        return "orders:" + userId;
    }
}
~~~

ExecutorService trong ví dụ được đóng bằng try-with-resources. Việc đóng executor chờ các tác vụ đã được submit hoàn tất theo hợp đồng của ExecutorService; ứng dụng cần tránh rời khỏi phạm vi quản lý khi còn task có thể giữ tài nguyên không được kiểm soát.

Virtual thread đặc biệt hữu ích cho workload có nhiều thao tác chờ I/O. Nó không làm một phép tính CPU-bound chạy nhanh hơn chỉ vì thread là virtual. Với tác vụ tính toán nặng, số lượng tác vụ chạy đồng thời vẫn cần được giới hạn theo số CPU và năng lực hệ thống.

### Kiểm tra virtual thread trong mã nguồn

Cách xác nhận trực tiếp nhất là biên dịch một đoạn mã dùng API Java 21:

~~~java
public class VirtualThreadCapability {
    public static void main(String[] args) throws Exception {
        Thread thread = Thread.startVirtualThread(
                () -> System.out.println(
                        "isVirtual = "
                                + Thread.currentThread().isVirtual()));
        thread.join();
    }
}
~~~

Nếu compiler không nhận diện Thread.startVirtualThread hoặc isVirtual(), compiler/toolchain đang dùng không cung cấp API tương ứng. Nếu biên dịch được nhưng runtime không hỗ trợ bytecode hoặc API đó, ứng dụng vẫn có thể thất bại khi chạy. Cần kiểm tra cả compiler lẫn runtime.

## 3. Structured concurrency và trạng thái preview

Structured concurrency cung cấp một cách tổ chức các tác vụ đồng thời theo cấu trúc lexical scope. Tác vụ cha mở một scope, fork các tác vụ con, chờ chúng hoàn thành hoặc hủy khi có lỗi, rồi đóng scope trước khi trả kết quả.

Ví dụ, một request cần tải hồ sơ người dùng và danh sách đơn hàng độc lập:

~~~text
Request cha
    |
    v
Mở task scope
    |
    +------> Tác vụ con: tải hồ sơ
    |
    +------> Tác vụ con: tải đơn hàng
    |
    v
Join / chờ kết quả
    |
    +------> Nếu lỗi: hủy các tác vụ còn lại theo chính sách
    |
    v
Đóng scope
    |
    v
Trả kết quả cho request cha
~~~

Khác với việc submit task vào một executor dùng chung rồi để task chạy độc lập, cấu trúc scope làm rõ ai sở hữu các tác vụ con và thời điểm nào chúng phải kết thúc. Khi request cha hoàn tất, các tác vụ con không nên tiếp tục chạy vô chủ và giữ tài nguyên của request cũ.

Structured concurrency được giới thiệu dưới dạng preview API từ Java 21 và tiếp tục được phát triển qua các bản JDK. Vì là preview, tên class, constructor, phương thức, kiểu trả về và chính sách shutdown có thể thay đổi giữa các lần preview. Không nên lấy một ví dụ từ JDK 21 rồi mặc định nó sẽ biên dịch nguyên vẹn trên JDK mới hơn.

Khi dùng structured concurrency, cần ghi rõ phiên bản JDK mà mã nguồn hướng tới. Đọc JEP và API documentation tương ứng với chính bản JDK đó, sau đó xác nhận bằng compiler của bản dựng. Nếu tính năng đã chuyển trạng thái trong một JDK tương lai, hãy dùng tài liệu của JDK đó để xác định API chính thức và bỏ các cờ preview không còn cần thiết.

### Ví dụ API preview phải gắn với phiên bản JDK

Ví dụ dưới đây minh họa kiểu sử dụng StructuredTaskScope trong một bản preview như Java 21. Nó là ví dụ theo phiên bản, không phải đoạn mã có thể dùng nguyên trạng cho mọi JDK:

~~~java
import java.util.concurrent.StructuredTaskScope;

public class StructuredTaskExample {
    public Response load(String userId) throws Exception {
        try (var scope =
                     new StructuredTaskScope.ShutdownOnFailure()) {
            var profile = scope.fork(() -> loadProfile(userId));
            var orders = scope.fork(() -> loadOrders(userId));

            scope.join();
            scope.throwIfFailed();

            return new Response(profile.get(), orders.get());
        }
    }

    private String loadProfile(String userId) {
        return "profile:" + userId;
    }

    private String loadOrders(String userId) {
        return "orders:" + userId;
    }

    public record Response(String profile, String orders) {}
}
~~~

Khi chuyển sang một bản JDK preview khác, hãy kiểm tra lại constructor, kiểu kết quả của fork, cách lấy kết quả và phương thức join/throwIfFailed. Việc dùng var trong ví dụ không loại bỏ yêu cầu tương thích API; compiler vẫn phải nhận diện đúng các method và kiểu trả về của phiên bản đang dùng.

## 4. Xác định JDK nào thực sự được dùng trong bản dựng

Một máy có thể cài nhiều JDK cùng lúc. Các lệnh java, javac, Gradle daemon, Gradle toolchain và runtime chạy ứng dụng có thể trỏ tới các bản JDK khác nhau.

Các lệnh kiểm tra cơ bản:

~~~shell
java -version
javac -version
gradlew.bat --version
gradlew.bat javaToolchains
~~~

Ý nghĩa:

- java -version hiển thị runtime được tìm thấy qua PATH trong terminal hiện tại.
- javac -version hiển thị compiler được tìm thấy qua PATH.
- gradlew.bat --version cho biết phiên bản Gradle và JVM chạy Gradle wrapper/daemon trong lần gọi đó.
- gradlew.bat javaToolchains liệt kê các toolchain JDK Gradle phát hiện được (khi Java plugin/toolchain support được cấu hình).

Kết quả của gradlew.bat --version không nhất thiết là compiler dùng để biên dịch source. Nếu dự án khai báo Java toolchain, Gradle có thể chọn một JDK khác cho compile/test. Ngược lại, một task JavaExec hoặc tiến trình được khởi chạy bên ngoài Gradle có thể dùng runtime khác.

Trong chính ứng dụng, có thể in phiên bản runtime:

~~~java
System.out.println("Runtime version: " + Runtime.version());
System.out.println("Runtime feature: " + Runtime.version().feature());
System.out.println("Current thread virtual: "
        + Thread.currentThread().isVirtual());
~~~

Đoạn kiểm tra isVirtual() cần được biên dịch bằng JDK có API Java 21 trở lên. Nếu ứng dụng cần chạy trên nhiều bản JDK, hãy đặt việc kiểm tra phiên bản ở module hoặc profile có source compatibility phù hợp.

## 5. Cấu hình Java toolchain cho Gradle

Java toolchain giúp bản dựng chọn JDK có phiên bản xác định thay vì phụ thuộc hoàn toàn vào PATH của máy phát triển.

Ví dụ cấu hình trong Gradle Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Khi cấu hình như trên, Gradle tìm toolchain Java 21 cho các task Java liên quan. Compiler và launcher của task có thể được chọn theo toolchain, trong khi JVM chạy Gradle vẫn là một khái niệm riêng.

Nếu dự án còn cấu hình sourceCompatibility, targetCompatibility hoặc options.release, hãy bảo đảm chúng nhất quán với toolchain và mục tiêu triển khai. Toolchain xác định JDK được dùng cho task; --release giới hạn API và bytecode mục tiêu. Hai cấu hình này không thay thế nhau.

Với virtual thread, nếu dự án compile bằng Java 21 trở lên và runtime triển khai cũng hỗ trợ Java 21 trở lên, không cần bật preview chỉ để dùng virtual thread.

## 6. Bật preview cho structured concurrency

Preview feature phải được bật ở cả giai đoạn biên dịch và runtime. Với Java 21 preview, compiler cần dùng đúng JDK 21 và cờ --enable-preview; runtime chạy bytecode preview cũng phải dùng JDK 21 cùng cờ này.

Ví dụ cấu hình Gradle Groovy DSL cho một dự án cố định ở JDK 21:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['--enable-preview']
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview'
}
~~~

Trong dự án thực tế, chỉ bật preview cho source set, module hoặc task cần sử dụng preview API. Không nên bật toàn cục nếu ứng dụng không cần preview, vì cờ này ảnh hưởng đến việc biên dịch và chạy các class dùng preview feature.

### Compiler và runtime phải cùng bản JDK preview

Preview feature gắn với bản phát hành JDK cụ thể. Ví dụ:

- Mã dùng preview API của JDK 21 phải được biên dịch bằng compiler JDK 21 với --enable-preview.
- Runtime JDK 21 phải có --enable-preview khi chạy class dùng preview.
- Compiler JDK mới hơn không thể dùng --enable-preview để tạo preview bytecode của một bản JDK cũ bằng cách đặt --release về bản cũ.
- Preview API có thể thay đổi hoặc bị loại bỏ ở bản phát hành tiếp theo; cần cập nhật source theo API của bản mới.

Vì vậy, sourceCompatibility = 21 hoặc options.release = 21 tự nó không chứng minh structured concurrency preview của JDK 21 đã được bật đúng. Cần kiểm tra cả phiên bản compiler và cờ preview.

## 7. Kiểm tra hỗ trợ theo từng lớp của build

Nên kiểm tra riêng từng lớp thay vì kết luận chỉ từ một lệnh java -version.

| Lớp kiểm tra | Điều cần xác nhận | Bằng chứng |
|---|---|---|
| JDK trên terminal | PATH đang trỏ tới bản nào | java -version, javac -version |
| Gradle runtime | JVM nào đang chạy Gradle | gradlew.bat --version |
| Gradle toolchain | JDK nào được chọn cho compile/test | gradlew.bat javaToolchains và cấu hình toolchain |
| Compiler | API virtual thread/structured concurrency có biên dịch được không | Chạy task compile với source thực tế |
| Test runtime | Preview flag có được truyền cho JVM test không | Chạy test sử dụng API preview |
| JavaExec/application | JVM khởi chạy ứng dụng có đúng JDK và cờ không | Chạy task thực tế hoặc kiểm tra launch configuration |
| Production runtime | JRE/JDK triển khai có hỗ trợ đúng bytecode/API không | Kiểm tra image/container và java -version tại môi trường chạy |
| CRaC runtime | Bản dựng có hỗ trợ checkpoint/restore cho cách dùng thread và thư viện không | Kiểm thử checkpoint/restore trên đúng JDK, vendor, OS và cấu hình |

Một bài compile pass chỉ chứng minh source tương thích với compiler/task đã chạy. Nó không chứng minh production runtime dùng cùng JDK, test JVM có cờ preview, hay CRaC runtime có thể checkpoint workload đó an toàn.

## 8. Cách tạo một capability check nhỏ

Đối với virtual thread, có thể thêm một chương trình nhỏ vào source set kiểm tra:

~~~java
import java.util.concurrent.Executors;

public class VirtualThreadProbe {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            executor.submit(() -> {
                System.out.println("virtual = "
                        + Thread.currentThread().isVirtual());
            }).get();
        }
    }
}
~~~

Đối với structured concurrency, capability probe cần được biên dịch bằng đúng JDK preview mục tiêu, với cờ preview cả ở compile và runtime. Probe nên gọi constructor và các method thực sự được ứng dụng sử dụng, bởi chỉ kiểm tra tên class tồn tại không bảo đảm toàn bộ API tương thích.

Không nên dùng reflection để cố phát hiện mọi biến thể preview rồi gọi method theo tên. API preview có thể thay đổi kiểu tham số, kiểu trả về và hành vi; compile-time check theo bản JDK mục tiêu thường cho kết quả rõ ràng hơn.

Sau khi probe thành công, vẫn cần chạy test của module và ứng dụng. Nếu dự án có nhiều module, mỗi module có thể dùng source set, toolchain hoặc compiler options riêng; không suy luận rằng một module compile thành công thì toàn bộ build đã dùng cùng cấu hình.

## 9. Virtual thread, structured concurrency và CRaC

CRaC khôi phục trạng thái tiến trình, trong đó có trạng thái JVM và các thành phần runtime được hỗ trợ. Nhưng việc dùng virtual thread hoặc structured concurrency không tự động bảo đảm ứng dụng có thể checkpoint ở bất kỳ thời điểm nào.

### Virtual thread đang hoạt động

Virtual thread là thread Java do JVM quản lý. Một virtual thread có thể đang chạy, chờ I/O, bị hủy hoặc hoàn tất. Khi checkpoint, ứng dụng cần xác định những tác vụ nào có thể tiếp tục sau restore và những tác vụ nào phải kết thúc trước đó.

Các câu hỏi cần trả lời:

- Virtual thread đang xử lý request có được phép tiếp tục từ trạng thái đã checkpoint không?
- Nó có đang giữ transaction, stream, socket hoặc lock không?
- Nó có đang ở giữa một side effect bên ngoài không?
- Nếu tác vụ bị chạy lại sau restore, nghiệp vụ có idempotent không?
- Runtime CRaC cụ thể có hỗ trợ trạng thái thread và thư viện đang dùng không?

Không nên giữ một virtual thread vô hạn chỉ để chờ sự kiện bên ngoài nếu nó đang giữ tài nguyên không thể phục hồi. Với tác vụ nền, cần có cơ chế stop, drain, cancel và resume rõ ràng.

### Structured task scope

Structured concurrency giúp giới hạn vòng đời tác vụ con trong scope. Đây là lợi thế khi chuẩn bị checkpoint: ứng dụng có thể ngừng tạo scope mới, chờ các scope hiện tại hoàn tất hoặc hủy tác vụ con theo chính sách, rồi mới chuyển tới trạng thái quiescent.

Một scope không tự động trở thành CRaC Resource. Thành phần quản lý request hoặc task scope vẫn cần tham gia vào cơ chế điều phối checkpoint để:

- Ngừng nhận yêu cầu tạo scope mới.
- Chờ các scope đang hoạt động kết thúc.
- Hủy scope theo quy tắc khi không thể chờ hoàn tất.
- Đảm bảo các tác vụ con đã đóng tài nguyên được sở hữu.
- Khởi động lại các tác vụ nền sau restore nếu nghiệp vụ yêu cầu.

Nếu scope đang chạy dở và bị checkpoint, không nên giả định việc restore sẽ đưa các tác vụ con và hệ thống bên ngoài trở lại cùng một trạng thái logic. Tác vụ con có thể đã gửi request hoặc ghi dữ liệu ra ngoài trước checkpoint.

### Pinning và native operation

Virtual thread thường được unmount khỏi carrier khi chờ ở các thao tác được JVM hỗ trợ. Tuy nhiên, một số đoạn code đồng bộ hoặc native operation có thể hạn chế khả năng unmount tùy JDK và loại thao tác. Điều này ảnh hưởng tới khả năng mở rộng và có thể làm việc dừng/drain thread khó dự đoán.

Hành vi pinning đã được cải thiện qua các bản JDK; không nên áp dụng kết luận của một phiên bản cho mọi phiên bản khác. Hãy xem tài liệu JDK mục tiêu, quan sát workload bằng công cụ chẩn đoán tương ứng và kiểm thử với thư viện native đang dùng.

## 10. Những lỗi cấu hình thường gặp

**Máy phát triển có JDK mới nhưng Gradle dùng toolchain cũ.**

Compiler được Gradle chọn có thể không nhận diện API virtual thread hoặc structured concurrency. Kiểm tra javaToolchains và cấu hình toolchain của task.

**Compile thành công nhưng test báo lỗi preview.**

Test JVM chưa nhận --enable-preview, hoặc test chạy bằng JDK khác với compiler đã tạo preview bytecode.

**Chỉ bật preview cho JavaCompile.**

Preview bytecode cũng cần được chạy bằng runtime phù hợp với cờ --enable-preview. Cấu hình Test, JavaExec và launcher production tương ứng.

**Dùng --release cũ với --enable-preview của JDK mới.**

Preview feature gắn với chính bản JDK compiler đang chạy. Không thể dùng cờ preview của JDK hiện tại để tạo preview API của một release cũ hơn.

**Structured concurrency sample không biên dịch trên JDK mới.**

API preview đã thay đổi giữa các bản phát hành. Đối chiếu code với JEP/API documentation của đúng JDK và cập nhật source theo phiên bản mục tiêu.

**Production chỉ cài JRE/JDK khác với build toolchain.**

Bytecode có thể dùng API mà production runtime không cung cấp. Cần kiểm tra runtime trong container hoặc máy triển khai, không chỉ kiểm tra môi trường phát triển.

**Cho rằng virtual thread tự giải quyết mọi vấn đề concurrency.**

Virtual thread không loại bỏ race condition, deadlock, giới hạn connection pool, giới hạn dịch vụ từ xa hay yêu cầu backpressure. Số lượng tác vụ đồng thời vẫn cần được kiểm soát theo tài nguyên mà chúng sử dụng.

**Cho rằng structured scope tự động an toàn cho checkpoint.**

Scope quản lý quan hệ giữa tác vụ cha và con; nó không tự dừng traffic, hoàn tất database transaction hoặc đảo ngược side effect bên ngoài. Cần nối scope với quy trình checkpoint của ứng dụng.

## 11. Quy trình xác nhận hỗ trợ trước khi đưa vào ứng dụng

Một quy trình thực tế có thể thực hiện theo thứ tự:

1. Xác định JDK mục tiêu và vendor/runtime sẽ chạy production.
2. Kiểm tra Gradle wrapper và JVM chạy Gradle.
3. Cấu hình Java toolchain rõ ràng cho module.
4. Xác nhận virtual thread bằng một capability probe trên JDK 21 trở lên.
5. Nếu dùng structured concurrency, xác định chính xác bản JDK preview và bật preview ở compile/test/runtime tương ứng.
6. Biên dịch và chạy unit test trên đúng toolchain.
7. Chạy integration test với database, HTTP client, broker và các thư viện thực tế.
8. Chạy ứng dụng bằng đúng runtime production và xác nhận API không bị thiếu.
9. Thực hiện checkpoint/restore trong lúc có workload đại diện, bao gồm tác vụ đang chờ I/O và task scope đang hoạt động.
10. Xác nhận sau restore không có task bị nhân đôi, transaction dở dang, connection cũ hoặc side effect bị lặp.

Khi nâng JDK, cần chạy lại capability probe và test checkpoint/restore. Không dựa vào việc build trước đó thành công để kết luận bản JDK mới có cùng API preview hoặc cùng hành vi CRaC.

## 12. Kết luận

Virtual thread là API chính thức từ Java 21; structured concurrency là API preview có thể thay đổi theo từng bản JDK. Việc kiểm tra hỗ trợ phải đi qua compiler, Gradle toolchain, test runtime, launcher ứng dụng và runtime production. Với preview API, compiler và runtime phải dùng đúng bản JDK tương ứng và được bật preview ở cả hai phía.

Trong ứng dụng CRaC, virtual thread và structured concurrency cần được đặt trong một quy trình quản lý vòng đời tác vụ rõ ràng. Ứng dụng phải ngừng tạo công việc mới, drain hoặc hủy tác vụ đang chạy, hoàn tất tài nguyên phụ thuộc và xác minh hành vi sau restore trên đúng bản dựng sẽ triển khai.
