# Đối chiếu hợp đồng preview trước khi chuyển từ Java 26 sang 27

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt API ổn định, preview API và incubator module khi nâng JDK.
- Kiểm kê các preview feature đang dùng ở Java 26 và đối chiếu với Java 27.
- Nhận diện thay đổi source, binary và hành vi runtime trong các API preview.
- Biên dịch và chạy preview code đúng JDK release.
- Hiểu vì sao class file phụ thuộc preview của Java 26 không thể chạy trên Java 27.
- Tổ chức build, test và phát hành riêng cho preview code.
- Kiểm tra thay đổi mặc định của JVM trong Java 27 ngoài phạm vi preview.
- Quyết định tính năng nào nên tiếp tục thử nghiệm, thay thế hoặc loại bỏ trước khi nâng cấp.

## 1. Vì sao phải kiểm tra lại hợp đồng preview?

Một preview feature được cung cấp để lập trình viên dùng thử và phản hồi. Nó đã được mô tả và triển khai trong một JDK cụ thể, nhưng chưa trở thành hợp đồng ổn định của Java SE. Sang release tiếp theo, feature có thể:

- Giữ nguyên và được preview lần nữa.
- Thay đổi tên lớp, method, generic type, exception hoặc semantics.
- Được hoàn thiện thành API ổn định.
- Bị rút lại hoặc loại bỏ.

Vì vậy, nâng từ JDK 26 lên JDK 27 không phải chỉ đổi version trong build file. Cần biên dịch lại và kiểm tra mọi nơi phụ thuộc vào preview API hoặc incubator API. Code có thể biên dịch ở JDK 26 nhưng không biên dịch ở JDK 27 dù tính năng vẫn mang cùng tên và tiếp tục ở trạng thái preview.

Java 27 phát hành GA ngày 15-09-2026. Tại ngày 27-11-2026, Oracle đã phát hành bản cập nhật JDK 27.0.1.1 ngày 17-11-2026. Khi thử nghiệm hoặc triển khai, dùng bản cập nhật mới nhất được vendor hỗ trợ và kiểm tra security baseline; không lấy bản GA ban đầu làm mặc định lâu dài. Java 25 vẫn là bản LTS mới nhất tại thời điểm này, còn Java 27 là feature release. Hãy tính cả vòng đời hỗ trợ khi chọn phiên bản production.

## 2. Bản đồ preview và incubator từ Java 26 sang 27

| Chủ đề | Java 26 | Java 27 | Trạng thái ở Java 27 |
|---|---|---|---|
| Primitive types in patterns, instanceof, switch | JEP 530, preview lần 4 | JEP 532, preview lần 5 | Preview ngôn ngữ |
| Lazy Constants | JEP 526, preview lần 2 | JEP 531, preview lần 3 | Preview API |
| Structured Concurrency | JEP 525, preview lần 6 | JEP 533, preview lần 7 | Preview API |
| PEM Encodings | JEP 524, preview lần 2 | JEP 538, preview lần 3 | Preview API |
| Vector API | JEP 529, incubator lần 11 | JEP 537, incubator lần 12 | Incubator module |

Java 27 có một preview language feature và ba nhóm preview API nêu trên. Vector API tiếp tục là incubator. Không có tính năng nào trong các nhóm này trở thành API ổn định chỉ vì đã trải qua nhiều vòng preview.

Có thể xem danh sách preview API chính thức của release trong Java SE 27 API Specification, và đối chiếu JEP của từng feature. Không suy ra trạng thái từ tên package hoặc từ việc code đã chạy được ở release trước.

## 3. Preview feature khác incubator module thế nào?

**Preview feature** là tính năng của ngôn ngữ, JVM hoặc API Java được cung cấp trong một release nhưng chưa vĩnh viễn. Ví dụ LazyConstant, StructuredTaskScope và PEM API. Để dùng preview feature, phải bật preview khi biên dịch và khi chạy bằng đúng release.

**Incubator module** là module thử nghiệm được cung cấp ngoài tập API chuẩn ổn định. Vector API thuộc module jdk.incubator.vector. Ứng dụng phải yêu cầu module này khi biên dịch và chạy. Incubator API cũng có thể đổi hoặc bị bỏ trong release sau.

Không nhầm hai cơ chế:

- Preview: dùng --enable-preview.
- Incubator: dùng --add-modules với tên module.
- Một ứng dụng có thể cần cả hai nếu đồng thời dùng preview API và incubator module.

Không dùng --enable-preview như một cách bật mọi incubator module. Cũng không thêm --add-modules để bật preview API.

## 4. Ràng buộc phiên bản của class file preview

Class file Java có cặp version major.minor. Java 26 dùng major version 70; Java 27 dùng major version 71. Khi class file phụ thuộc preview feature của release, minor version là 65535.

| Release | Class file major | Class file preview |
|---|---:|---|
| Java 26 | 70 | 70.65535 |
| Java 27 | 71 | 71.65535 |

JVM Java 27 không được phép nạp class file 70.65535 phụ thuộc preview Java 26, kể cả khi bật --enable-preview. Class file preview bị gắn với release đã định nghĩa feature vì phiên bản sau có thể đã đổi hoặc bỏ feature.

Class file không dùng preview, được biên dịch với target phù hợp, thường có minor version 0 và có thể chạy trên JDK mới hơn nếu không phụ thuộc API đã bị loại bỏ. Điều này không làm cho preview class tương thích chéo release.

Có thể kiểm tra version của class file:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

Tìm hai dòng major version và minor version trong kết quả. Khi dùng preview Java 27, class file có thể hiện major version 71 và minor version 65535.

## 5. Biên dịch và chạy preview đúng release

Muốn dùng preview feature của Java 27, dùng compiler JDK 27 với --enable-preview và --release 27:

~~~bash
javac --enable-preview --release 27 -Xlint:preview -d out src/com/example/Main.java
java --enable-preview -cp out com.example.Main
~~~

Không dùng compiler JDK 27 với --enable-preview --release 26 để cố tạo class file preview Java 26. Compiler chỉ bật preview cho release hiện tại của chính nó. Nếu cần giữ một artifact preview Java 26 để chạy trên JDK 26, phải dùng toolchain JDK 26 và pipeline riêng.

Đối với Java 26, lệnh tương ứng là:

~~~bash
javac --enable-preview --release 26 -Xlint:preview -d out26 src/com/example/Main.java
java --enable-preview -cp out26 com.example.Main
~~~

Khi chuyển sang 27, phải biên dịch lại source bằng JDK 27, xử lý các lỗi do API thay đổi, rồi chạy test trên JDK 27. Không copy class file preview Java 26 sang image runtime Java 27.

Với ứng dụng nhiều module hoặc build tool, bảo đảm compiler task, test JVM, integration test, công cụ chạy migration và runtime container đều nhận đúng tùy chọn. Chỉ thêm cờ vào task compile mà quên test/runtime sẽ tạo ra lỗi khi chạy.

## 6. Primitive patterns: preview lần 4 sang lần 5

Java 26 dùng JEP 530; Java 27 dùng JEP 532. Cả hai vẫn là preview language feature. JLS Java 27 ghi nhận lần preview thứ năm không có thay đổi chuẩn tắc đối với định nghĩa ngôn ngữ so với lần preview Java 26. Tuy vậy, code vẫn phải được biên dịch lại bằng JDK 27 và class file preview Java 26 không thể được dùng trực tiếp.

Feature này mở rộng pattern matching để làm việc với primitive types trong các pattern context, instanceof và switch. Phần quan trọng của thiết kế là exact numeric conversion: phép kiểm tra chỉ khớp khi chuyển đổi không làm mất thông tin và không ném exception.

Ví dụ minh họa dạng pattern:

~~~java
static String describe(Object value) {
    return switch (value) {
        case int number -> "int: " + number;
        case long number -> "long: " + number;
        default -> "other";
    };
}
~~~

Đây là cú pháp preview của JDK 27; không dùng nó trong source cần biên dịch bằng JDK 25 hoặc release không hỗ trợ feature.

**Rủi ro vòng đời cần biết:** ngày 09-11-2026, nhóm đặc tả Amber thông báo ngừng phát triển Primitive Types in Patterns và sẽ loại bỏ feature khỏi JDK 28. JDK 27 vẫn có JEP 532 preview lần 5, nhưng đây là phiên bản cuối cùng dự kiến có feature này. Không chọn primitive patterns làm nền tảng cho code dài hạn hoặc API thư viện công khai; nếu đang thử nghiệm, cô lập code để có thể thay thế.

## 7. Lazy Constants: API và hành vi lỗi đã thay đổi

JDK 26 dùng JEP 526, preview lần 2; JDK 27 dùng JEP 531, preview lần 3. Đây là một trong những thay đổi cần rà soát kỹ vì có cả thay đổi chữ ký API lẫn semantics runtime.

### Method đã có ở Java 26 nhưng không còn ở Java 27

Trong JDK 26, LazyConstant có:

- isInitialized(): kiểm tra constant đã được khởi tạo hay chưa.
- orElse(other): đọc giá trị nếu đã khởi tạo, nếu chưa thì trả về giá trị thay thế mà không khởi tạo.

Hai method này không còn trong API LazyConstant của JDK 27. Source gọi chúng sẽ không biên dịch khi chuyển sang JDK 27. Không thay chúng bằng get() một cách máy móc vì get() kích hoạt tính toán.

Nếu ứng dụng cần quan sát trạng thái khởi tạo, hãy xem lại mục tiêu thiết kế. Trạng thái lazy constant không nên được dùng như một cờ nghiệp vụ có thể thay đổi. Nếu cần một trạng thái công khai, hãy mô hình hóa bằng kiểu ứng dụng riêng thay vì phụ thuộc vào method preview đã bị bỏ.

### Semantics khi computing function thất bại

Trong Java 26, nếu computing function ném exception, exception được truyền về caller và constant vẫn chưa khởi tạo; lần gọi get() sau có thể thử tính toán lại.

Trong Java 27, nếu computing function ném unchecked exception hoặc trả về null, LazyConstant chuyển sang trạng thái lỗi. Lần truy cập đầu nhận NoSuchElementException với nguyên nhân; các lần get() tiếp theo tiếp tục nhận NoSuchElementException và không gọi lại computing function. Trường hợp đệ quy cũng chuyển thành trạng thái lỗi, với IllegalStateException là nguyên nhân.

Đây là thay đổi hành vi quan trọng. Nếu supplier phụ thuộc vào dịch vụ có thể tạm thời lỗi, code Java 26 có thể thử lại ở lần get() sau, trong khi Java 27 giữ constant ở trạng thái lỗi. Không dùng LazyConstant cho thao tác cần retry tự động. Nếu cần retry, hãy đặt cơ chế retry bên trong supplier trước khi supplier hoàn tất hoặc dùng một abstraction retry có trạng thái rõ ràng.

Ví dụ:

~~~java
static final LazyConstant<Settings> SETTINGS =
    LazyConstant.of(Settings::load);

Settings settings = SETTINGS.get();
~~~

Supplier nên có kết quả ổn định, chỉ khởi tạo một lần và có chính sách lỗi phù hợp. LazyConstant không cung cấp timeout hoặc cancellation; nếu supplier chặn vô hạn, các thread khác chờ cùng constant cũng có thể bị chặn.

### Set.ofLazy được thêm trong Java 27

Java 26 đã có List.ofLazy và Map.ofLazy. Java 27 bổ sung Set.ofLazy(Set, Predicate), tạo một tập không sửa đổi với membership được tính khi cần. List.ofLazy, Map.ofLazy và Set.ofLazy đều cần preview flag.

Các lazy collection này có thể giữ computing function trong thời gian còn phần tử chưa tính. Những thao tác như contains, get, values, entrySet, equals, hashCode hoặc toString có thể kích hoạt tính toán tùy loại collection. Không giả định một phép debug/log đơn giản sẽ không kích hoạt supplier.

## 8. Structured Concurrency: thay đổi generic và exception contract

JDK 26 dùng JEP 525, preview lần 6; JDK 27 dùng JEP 533, preview lần 7. API đã thay đổi đáng kể về kiểu generic và cách biểu diễn lỗi của join.

| Thành phần | Java 26 | Java 27 |
|---|---|---|
| StructuredTaskScope | StructuredTaskScope<T,R> | StructuredTaskScope<T,R,R_X extends Throwable> |
| Joiner | Joiner<T,R> | Joiner<T,R,R_X extends Throwable> |
| Exception mặc định khi subtask lỗi | StructuredTaskScope.FailedException | ExecutionException |
| Timeout exception trong Joiner | onTimeout() | timeout() |
| Exception nguyên nhân timeout | TimeoutException | CancelledByTimeoutException |

Ở Java 27, generic parameter thứ ba mô tả kiểu exception mà join() có thể ném. Khi dùng Joiner tự triển khai, phải cập nhật type parameter, chữ ký method và chính sách lỗi. Không chỉ sửa import để đổi FailedException thành ExecutionException; hãy kiểm tra kiểu R_X và exception mà Joiner thực sự trả về.

Ví dụ xử lý mặc định ở Java 27:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var first = scope.fork(() -> fetchFirst());
    var second = scope.fork(() -> fetchSecond());

    scope.join();

    return combine(first.get(), second.get());
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    // Ánh xạ lỗi nghiệp vụ theo cause.
}
~~~

Nếu dùng timeout, Java 27 có thể ném ExecutionException với CancelledByTimeoutException làm cause. Joiner tùy chỉnh có thể chọn kiểu kết quả và exception khác; không giả định mọi join() đều chỉ ném ExecutionException.

Trong Java 26, code thường bắt StructuredTaskScope.FailedException và Joiner có onTimeout(). Khi nâng lên Java 27, cập nhật catch block, generic declaration và implementation Joiner. Test các trường hợp subtask thành công, một subtask lỗi, nhiều subtask lỗi, timeout, cancellation và thread interruption.

Subtask phải phản hồi interrupt để close() có thể kết thúc đúng lúc. Structured concurrency không tự bảo đảm task dừng nhanh nếu code bên trong chặn ở thao tác không interruptible.

## 9. PEM API: đổi DEREncodable thành BinaryEncodable

JDK 26 dùng JEP 524, preview lần 2; JDK 27 dùng JEP 538, preview lần 3. API được mở rộng và đổi tên để phản ánh rằng đối tượng có thể cung cấp dạng nhị phân, không chỉ DER.

Các thay đổi source cần rà soát:

| Java 26 | Java 27 |
|---|---|
| DEREncodable | BinaryEncodable |
| PEM là record | PEM là final class |
| PEM.content() trả String | PEM.content() trả byte[] Base64 |
| PEMDecoder.withFactory(provider) | PEMDecoder.withFactoriesOf(provider) |
| PEMDecoder trả DEREncodable | PEMDecoder trả BinaryEncodable |
| Dữ liệu leadingData có thể bị thay đổi qua mảng gốc | PEM class bảo vệ mảng bằng defensive copy |

Do PEM không còn là record, code dùng record pattern, record component hoặc giả định semantics equals/hashCode của record phải được viết lại. Method content() đổi kiểu trả về từ String sang byte[] nên code gọi content() sẽ cần kiểm tra và cập nhật.

Trong JDK 27, PEM cung cấp content() để lấy Base64 bytes và decode() để lấy nội dung binary đã giải mã Base64. leadingData() trả bản sao. Constructor có tham số mảng cũng sao chép dữ liệu đầu vào; các tham số bắt buộc không được null. Đây là thay đổi quan trọng về ownership của byte array.

Ví dụ đọc PEM không được hỗ trợ thành lớp khóa/certificate cụ thể:

~~~java
PEMDecoder decoder = PEMDecoder.of();
BinaryEncodable decoded = decoder.decode(pemText);

if (decoded instanceof PEM pem) {
    byte[] base64 = pem.content();
    byte[] binary = pem.decode();
}
~~~

Đối với Provider, đổi withFactory() thành withFactoriesOf(). API Java 27 cũng bổ sung CryptoException cho một số lỗi mã hóa/giải mã, thêm các overload encrypt nhận BinaryEncodable và getKey(Key)/getKeyPair(Key). Hãy cập nhật catch block và test password decryption, provider selection, key pair và dữ liệu PEM không có class tương ứng.

Không dùng preview PEM API để lưu trữ khóa production nếu chưa chấp nhận rủi ro thay đổi ở release kế tiếp. Nếu cần dùng, hãy giữ lớp adapter ở ranh giới bảo mật và test với certificate, private key, CRL, encrypted private key cùng các loại PEM khác mà hệ thống nhận.

## 10. Vector API vẫn là incubator

Java 26 dùng JEP 529, incubator lần 11; Java 27 dùng JEP 537, incubator lần 12. API tiếp tục nằm trong module jdk.incubator.vector. Đây không phải preview API và chưa phải Java SE API ổn định.

Với classpath, thêm module khi biên dịch và chạy:

~~~bash
javac --release 27 --add-modules jdk.incubator.vector -d out src/com/example/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out com.example.VectorDemo
~~~

Với named module, khai báo:

~~~java
module com.example.app {
    requires jdk.incubator.vector;
}
~~~

Không cần --enable-preview chỉ để dùng Vector API. Nếu source đồng thời dùng preview language/API thì vẫn cần bật preview riêng.

Vector API phụ thuộc kiến trúc CPU, vector species, lane count và khả năng SIMD của máy chạy. Không giả định mọi CPU có cùng độ rộng vector hoặc đều tăng tốc. Dùng VectorSpecies.PREFERRED, kiểm thử phần đuôi mảng, mask, alignment, overflow semantics và so sánh với scalar implementation bằng benchmark trên phần cứng đích.

Vì đây là incubator module, giữ code Vector API trong adapter hoặc module riêng. Không để public API ổn định của thư viện phụ thuộc trực tiếp vào type incubator nếu người dùng thư viện không kiểm soát JDK runtime.

## 11. Những thay đổi JVM mặc định cần kiểm tra dù không phải preview

Nâng cấp từ Java 26 lên 27 còn thay đổi mặc định runtime. Những thay đổi này không yêu cầu preview flag nhưng có thể ảnh hưởng vận hành:

| Thay đổi | Java 27 | Kiểm tra khi nâng cấp |
|---|---|---|
| G1 trở thành GC mặc định trong mọi môi trường | JEP 523 | Đo pause, throughput, heap và CPU nếu ứng dụng không chỉ định GC |
| Compact Object Headers mặc định bật | JEP 534 | Kiểm tra native agent, JNI, công cụ instrumentation và thư viện phụ thuộc layout object; đo footprint và hiệu năng |
| Hybrid post-quantum key exchange cho TLS 1.3 | JEP 527 | Kiểm tra handshake với proxy, load balancer, firewall và peer cũ |
| JFR in-process data redaction | JEP 536 | Kiểm tra dashboard/automation không còn phụ thuộc command-line args hoặc giá trị ban đầu của environment/system properties đã bị redacted |
| Cảnh báo deep reflection sửa final field | JEP 500 | Chạy test serialization, DI, ORM và thư viện có dùng reflection; lập kế hoạch loại bỏ mutation trái phép |

Nếu ứng dụng đã chỉ định rõ GC, thay đổi default G1 không nhất thiết tác động đến ứng dụng đó. Với TLS, các ứng dụng dùng javax.net.ssl có thể nhận hybrid key exchange mặc định, nhưng cần kiểm tra khả năng tương thích của các thiết bị mạng và peer bên ngoài. Với JFR, redaction giúp giảm rò rỉ secret nhưng có thể làm một số trường chẩn đoán không còn xuất hiện trong recording.

## 12. Lập inventory trước khi thay JDK

Trước khi đổi toolchain, tìm mọi nơi sử dụng preview hoặc incubator:

- Source code có import java.util.concurrent.StructuredTaskScope, java.lang.LazyConstant, java.security.PEM, java.security.PEMEncoder/Decoder.
- Code có gọi LazyConstant.isInitialized(), LazyConstant.orElse(), Joiner.onTimeout(), PEMDecoder.withFactory().
- Code có tham chiếu DEREncodable, PEM.content() theo kiểu String hoặc record pattern với PEM.
- Module descriptor hoặc build option có jdk.incubator.vector.
- Compiler flags và runtime flags có --enable-preview.
- Dependency bên thứ ba có class file preview hoặc module incubator.
- Plugin, annotation processor, test fixture, code generator và công cụ phân tích có phụ thuộc API preview.
- Docker image, launch script, systemd service, CI agent và môi trường developer có JDK version khác nhau.

Dùng tìm kiếm source và build configuration để xác định nơi cần cập nhật. Kiểm tra Javadoc Preview List của JDK 26 và 27; đọc JEP history để biết thay đổi theo từng vòng preview. Không chỉ tìm tên JEP vì một API có thể đổi tên hoặc method trước đây biến mất.

Có thể dùng javac với -Xlint:preview để phát hiện nơi source dùng preview feature. Đọc cảnh báo khi compile, không tắt lint chỉ để build sạch. Với binary phụ thuộc preview, dùng javap -verbose để kiểm tra major/minor version.

## 13. Chiến lược chuyển đổi theo từng nhóm

| Nhóm | Chiến lược |
|---|---|
| API ổn định Java SE | Biên dịch lại, chạy regression test và kiểm tra API/deprecation |
| Primitive patterns preview | Recompile bằng JDK 27; chỉ dùng trong thử nghiệm có thể thay thế; lưu ý sẽ bị bỏ ở JDK 28 |
| Lazy Constants preview | Xóa isInitialized/orElse; cập nhật error handling và test supplier failure |
| Structured Concurrency preview | Sửa generic arity, Joiner, catch exception và timeout |
| PEM preview | Đổi BinaryEncodable, cập nhật PEM accessor, decoder/provider và exception |
| Vector incubator | Cập nhật module resolution, benchmark trên CPU đích và cô lập adapter |

Không nâng cùng lúc JDK, framework, ORM, JDBC driver, GC flags và thuật toán ứng dụng nếu không cần thiết. Giữ một biến thay đổi chính trong mỗi vòng benchmark để biết lỗi hoặc chênh lệch đến từ đâu.

## 14. Build pipeline cho preview code

Tách preview code khỏi phần production ổn định bằng source set hoặc module riêng. Ví dụ:

~~~text
application/
  src/main/                 # API ổn định
  src/preview27/            # Java 27 preview
  src/vector27/             # Vector incubator
  test/
  build/
~~~

Phần main không dùng preview API. Preview source set biên dịch bằng JDK 27 với --enable-preview --release 27; test JVM cũng phải chạy bằng JDK 27 với --enable-preview. Vector source set cần --add-modules jdk.incubator.vector ở compile và runtime.

Đặt JDK toolchain rõ ràng trong Maven/Gradle/CI. Không dựa vào JAVA_HOME ngẫu nhiên trên máy developer. Ghi lại vendor, version, build và flags trong build metadata để tái tạo được artifact.

Nếu phát hành binary dùng preview feature, giới hạn rõ runtime tương thích và đánh dấu artifact là thử nghiệm. Không đưa preview API vào public API của SDK hoặc thư viện dùng chung cho nhiều JDK release.

## 15. Ma trận kiểm thử sau khi chuyển lên JDK 27

Chạy các nhóm kiểm thử sau:

1. **Compile:** biên dịch toàn bộ module bằng JDK 27; bật -Xlint:preview; xác nhận không còn method hoặc type preview cũ.
2. **Runtime:** chạy với và không có --enable-preview theo đúng loại artifact; bảo đảm class preview chỉ chạy trên JDK 27.
3. **Structured concurrency:** test success, subtask exception, cancellation, timeout, interrupt và close.
4. **Lazy constants:** test khởi tạo đồng thời, supplier trả null, supplier ném exception, đệ quy và truy cập sau trạng thái lỗi.
5. **PEM:** test key/certificate/CRL, PEM lạ, leading data, byte array defensive copy, encrypted private key và Provider.
6. **Vector:** test scalar fallback, preferred species, mask, tail elements, overflow và CPU architectures hỗ trợ.
7. **GC/runtime:** đo startup, allocation, heap, pause, throughput với G1 và Compact Object Headers.
8. **TLS:** test handshake TLS 1.3 với peer, proxy và thiết bị mạng thực tế.
9. **Observability:** kiểm tra JFR redaction và các dashboard dựa trên command line/environment properties.
10. **Native integration:** kiểm thử JNI, JVMTI agent và thư viện thao tác trực tiếp với object layout.

Không chỉ chạy unit test. Các thay đổi concurrency, TLS, GC và native integration cần integration test trên môi trường production-like.

## 16. Ví dụ checklist go/no-go

Có thể dùng các điều kiện sau trong release gate:

- Không còn class file preview Java 26 trong artifact Java 27.
- Mọi preview source đã compile bằng JDK 27 và chạy trên JDK 27.
- Mọi incubator module được khai báo rõ ràng trong compile/runtime/module descriptor.
- Không còn lời gọi API đã bị xóa hoặc đổi kiểu trả về.
- Exception handling của LazyConstant và StructuredTaskScope đã được cập nhật.
- PEM adapter xử lý BinaryEncodable và byte[] đúng ownership.
- TLS 1.3 hybrid handshake được kiểm tra với hệ thống bên ngoài.
- GC và Compact Object Headers có baseline hiệu năng mới.
- JFR dashboards chấp nhận các trường đã redacted.
- Runtime production dùng đúng bản cập nhật JDK được tổ chức phê duyệt.
- Có rollback artifact và runtime image về phiên bản đã kiểm thử trước đó.

Nếu một preview feature là bắt buộc nhưng chưa ổn định, release gate phải ghi rõ owner, phạm vi sử dụng, JDK version và kế hoạch thay thế. Không coi việc build thành công là bằng chứng feature đã sẵn sàng cho production.

## 17. Trạng thái phiên bản và tài liệu chuẩn

Tại ngày 27-11-2026:

- JDK 27 đã GA từ ngày 15-09-2026.
- JDK 27.0.1.1 phát hành ngày 17-11-2026 là bản cập nhật mới nhất được Oracle công bố tại thời điểm này.
- JDK 25 là release LTS mới nhất.
- Primitive Patterns vẫn là preview trong JDK 27 nhưng đã có thông báo sẽ bị loại khỏi JDK 28.
- Lazy Constants, Structured Concurrency và PEM vẫn là preview API.
- Vector API vẫn là incubator module.

Các trạng thái này có thể thay đổi ở release tiếp theo. Luôn đọc preview-list và release notes của đúng JDK build sẽ chạy ở production.

## Kết luận

Trước khi chuyển Java 26 sang 27, hãy kiểm tra từng preview contract chứ không chỉ kiểm tra JEP còn tồn tại. Primitive patterns vẫn preview nhưng sẽ bị bỏ ở JDK 28; Lazy Constants đã bỏ isInitialized/orElse và đổi cách xử lý supplier failure; Structured Concurrency đổi generic, Joiner và exception; PEM đổi DEREncodable thành BinaryEncodable và đổi PEM từ record thành class; Vector API tiếp tục là incubator. Preview class file bị gắn với release nên class preview Java 26 không chạy trên Java 27. Biên dịch lại bằng JDK 27, cập nhật API, chạy test hành vi và kiểm tra các thay đổi runtime như G1, Compact Object Headers, TLS hybrid key exchange và JFR redaction. Chỉ phát hành khi build, runtime, module flags và JDK patch version đã được xác định rõ.

## Tài liệu tham khảo

- [Oracle JDK 27 – Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Oracle JDK 27 – Preview API List](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html)
- [Oracle JDK 27 – Preview Language and VM Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [Java Virtual Machine Specification, Java SE 27 – Preview Feature Restrictions](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html)
- [Java Language Changes Summary – Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [JEP 531 – Lazy Constants (Third Preview)](https://openjdk.org/jeps/531)
- [JEP 533 – Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [JEP 538 – PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538)
- [JEP 537 – Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [JEP 532 – Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532)
- [Oracle Java SE 26 API – LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Oracle Java SE 27 API – LazyConstant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [Oracle Java SE 26 API – StructuredTaskScope](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Oracle Java SE 27 API – StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Oracle Java SE 26 API – PEM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEM.html)
- [Oracle Java SE 27 API – BinaryEncodable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html)
- [Oracle Java SE 27 API – PEM](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEM.html)
- [OpenJDK Amber – Withdrawing the Primitive Patterns preview feature, 09-11-2026](https://www.mail-archive.com/amber-spec-experts%40openjdk.org/msg00923.html)
- [Oracle JDK 27.0.1.1 Release Notes, 17-11-2026](https://www.oracle.com/java/technologies/javase/27-0-1-1-relnotes.html)
