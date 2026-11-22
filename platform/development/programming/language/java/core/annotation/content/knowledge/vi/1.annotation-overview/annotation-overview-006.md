# Khi nào dùng annotation, marker interface hoặc cấu hình bên ngoài trong Java?

Khi thiết kế một thư viện hoặc ứng dụng Java, cùng một yêu cầu “đánh dấu để hệ thống xử lý khác đi” có thể dẫn tới ba lựa chọn: **annotation**, **marker interface (giao diện đánh dấu)** hoặc **cấu hình bên ngoài**. Chúng có thể phối hợp, nhưng mang ý nghĩa khác nhau. Chọn đúng cơ chế giúp người đọc API hiểu được ý định, chương trình kiểm tra được điều cần kiểm tra và người vận hành thay đổi được những tham số thực sự cần điều chỉnh.

## 1. Phân biệt theo câu hỏi cần giải quyết

- **Annotation** trả lời “khai báo/lớp/phương thức này có metadata gì để công cụ hoặc framework đọc?”. Ví dụ, một phương thức được gắn tên metric, một kiểu được đăng ký với bộ xử lý, một tham số cần validation.
- **Marker interface** trả lời “đối tượng thuộc một nhóm kiểu nào mà API có thể nhận diện?”. Nó là interface không khai báo phương thức, nhưng việc một lớp **implements** interface đó là một phần của hệ thống kiểu Java. Ví dụ kinh điển: **Serializable**, **RandomAccess**.
- **Cấu hình bên ngoài** trả lời “giá trị, chính sách hoặc tham số nào có thể khác nhau giữa môi trường/lần triển khai mà không cần thay đổi mã khai báo?”. Ví dụ mức logging, timeout, giới hạn batch, bật/tắt telemetry.

Một quy tắc hữu ích: **annotation mô tả**, **marker interface phân loại ở mức kiểu**, còn **cấu hình cung cấp giá trị/chính sách vận hành**. Cả ba chỉ tạo tác dụng khi có đoạn mã hoặc công cụ thực sự sử dụng chúng; đặc biệt, annotation tự định nghĩa không tự thực thi nghiệp vụ.

| Tiêu chí | Annotation | Marker interface | Cấu hình bên ngoài |
| --- | --- | --- | --- |
| Gắn vào đâu? | Khai báo Java theo phạm vi **@Target**: class, method, field, parameter… | Lớp/kiểu implements interface | File, biến môi trường, tham số chạy, config service hoặc DB |
| Giá trị biểu đạt | Metadata, thuộc tính của khai báo, quy tắc để processor đọc | Tư cách thành viên một tập kiểu | Giá trị và chính sách thay đổi được theo môi trường |
| Kiểm tra tại compile time | Trình biên dịch/annotation processor có thể kiểm tra nếu có cơ chế phù hợp | Có thể dùng như kiểu tham số hoặc giới hạn generic **extends** | Thường phải parse/validate khi nạp cấu hình |
| Nhận diện runtime | Có thể dùng reflection nếu retention là **RUNTIME**; hoặc qua framework | **instanceof**, kiểm tra assignability | Đọc giá trị đã nạp; reload phụ thuộc thiết kế |
| Có tham số? | Có, thông qua annotation elements | Interface rỗng không mang tham số riêng | Có, dưới dạng các khóa/giá trị |
| Đổi chính sách không sửa code? | Đổi annotation trong source thường cần build lại | Đổi implements thường cần build lại | Có thể đổi nguồn cấu hình; việc áp dụng tức thời hay sau restart do ứng dụng quyết định |
| Phù hợp nhất | Metadata bám theo khai báo | Ràng buộc phân loại ở mức Java type | Điều chỉnh hoạt động theo môi trường hoặc vận hành |

Không nên suy từ bảng rằng annotation luôn mạnh hơn marker, hoặc config luôn thay được annotation. Chúng đang giải quyết những câu hỏi khác nhau.

## 2. Khi nào chọn annotation?

Dùng annotation khi thông tin **gắn với một khai báo cụ thể**, có cấu trúc rõ ràng, và đã xác định **ai sẽ đọc thông tin đó để làm gì**.

Ví dụ thường gặp:

- **@Override** giúp trình biên dịch kiểm tra ý định override phương thức; không phải một “công tắc runtime”.
- **@Deprecated** thông báo API không còn được khuyến nghị sử dụng.
- **@Test** của JUnit đánh dấu phương thức để test engine phát hiện và chạy; JUnit là thư viện bổ sung, không phải cơ chế do Java tự kích hoạt.
- **@Transactional** của Spring cung cấp metadata để hạ tầng Spring xử lý transaction trong những điều kiện proxy/weaving phù hợp; việc chỉ đặt annotation lên một phương thức bất kỳ không bảo đảm transaction được áp dụng.

Một annotation tự định nghĩa có thể như sau (đây là **đoạn minh họa khai báo**, ví dụ chạy đầy đủ ở mục 5):

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Measured {
    String value();
}
~~~

**@Target(METHOD)** giới hạn nơi sử dụng; **@Retention(RUNTIME)** giữ metadata để code runtime có thể gọi reflection, chẳng hạn **Method.getAnnotation(Measured.class)**. Phương thức gắn **@Measured("checkout")** vẫn chạy như bình thường nếu không có bộ xử lý nào đọc và sử dụng annotation này.

### Retention và thời điểm xử lý

| Retention | Có mặt ở đâu? | Cách dùng điển hình |
| --- | --- | --- |
| **SOURCE** | Trong source; không được giữ trong file class | Quy tắc/phân tích trong quá trình biên dịch |
| **CLASS** | Trong class file, thường không truy cập qua reflection runtime | Phân tích/biến đổi bytecode, công cụ build |
| **RUNTIME** | Trong class file và có thể đọc bằng reflection runtime | Framework hoặc thư viện khám phá metadata khi chạy |

Nếu không khai báo **@Retention**, giá trị mặc định là **CLASS**. Gắn **RUNTIME** không có nghĩa JVM sẽ tự đăng ký handler; nó chỉ làm metadata hiện diện để chương trình có thể đọc. Annotation processor tại compile time và reflection tại runtime là **hai cách tiêu thụ metadata khác nhau**. Hãy chọn retention theo nhu cầu thực tế, không tự động dùng RUNTIME cho tất cả annotation.

### Dấu hiệu annotation là lựa chọn tốt

1. Metadata áp dụng cho từng phương thức/field/parameter, nơi marker interface không biểu đạt được một cách tự nhiên.
2. Cần thuộc tính như tên, nhóm, mức độ, tên cột… và các thuộc tính đó là đặc điểm ổn định của khai báo.
3. Framework/processor đã có cơ chế quét, diễn giải, kiểm tra hoặc sinh mã từ annotation.
4. Muốn đặt khai báo gần code liên quan để người bảo trì đọc trực tiếp.

**Không nên** thêm annotation chỉ để trang trí: nếu không có consumer, “đã đánh dấu” không tạo chức năng. Tránh dùng annotation hard-code những giá trị đáng ra mỗi môi trường phải cấu hình, như URL sản xuất hay mật khẩu. Nếu metadata ngày càng chứa logic điều kiện và workflow phức tạp, một API hoặc đối tượng cấu hình rõ ràng thường dễ kiểm thử hơn.

## 3. Khi nào chọn marker interface?

Marker interface là interface **không khai báo phương thức**, dùng để nói rằng một đối tượng thuộc một nhóm kiểu mà thư viện quan tâm. Ví dụ:

~~~java
interface BatchEligible {
}

final class ReportJob implements BatchEligible {
}
~~~

Đoạn trên **không** tự làm **ReportJob** chạy theo batch. Nhưng Java biết **ReportJob** là một **BatchEligible**:

~~~java
static <T extends BatchEligible> void enqueue(T job) {
    // Chỉ nhận kiểu implements BatchEligible.
}
~~~

Đây là ví dụ **đoạn mã bên trong một lớp**, không phải chương trình độc lập. Lời gọi **enqueue(new ReportJob())** hợp lệ; một kiểu không implements **BatchEligible** sẽ bị trình biên dịch từ chối tại call site với kiểu cụ thể không tương thích. Marker cũng có thể được kiểm tra bằng **instanceof** hoặc **BatchEligible.class.isAssignableFrom(...)** trong bộ điều phối runtime.

Trong Java chuẩn:

- **java.io.Serializable** là marker để cơ chế Java serialization nhận biết đối tượng có thể tham gia quy trình serialization theo hợp đồng của API. Việc implements interface không bảo đảm mọi object graph đều serialize thành công.
- **java.util.RandomAccess** báo hiệu một danh sách có hỗ trợ truy cập chỉ số nhanh theo ý đồ thiết kế API; thư viện có thể dùng marker này để chọn thuật toán. Đây là lời hứa đặc tính, không phải JVM tự tối ưu mọi lời gọi.

### Dùng marker interface khi

- Cần **ràng buộc ở mức kiểu** cho chữ ký API, generic bound, hoặc phân nhóm qua **instanceof**.
- Một framework hoặc thư viện hiện có **đã công bố hợp đồng marker** và cần tương thích với nó.
- Tư cách thành viên phải ổn định theo kiểu và không cần tham số riêng cho từng method hay môi trường.

### Khi marker interface không phù hợp

Nếu đối tượng cần thực sự cung cấp thao tác, hãy dùng **interface có phương thức**. Ví dụ **Runnable.run()** diễn đạt khả năng thực thi, còn marker rỗng không ép lớp thực hiện thao tác gì. Nếu chỉ cần metadata cho một method cụ thể, annotation chính xác hơn. Nếu muốn thay giới hạn batch từ 5 sang 10 ở production, thêm interface **BatchSize10** không hợp lý: đó là cấu hình.

Cũng cần cân nhắc rằng **implements** là quyết định về type contract, làm thay đổi quan hệ kiểu của class; không phù hợp cho những cờ vận hành thay đổi thường xuyên.

## 4. Khi nào chọn cấu hình bên ngoài?

Dùng cấu hình bên ngoài cho **tham số hoặc chính sách có thể thay đổi mà không phải sửa source**, đặc biệt khi khác nhau giữa dev, staging, production hoặc theo cách vận hành. Các nguồn phổ biến là:

- File **.properties** (được Java hỗ trợ qua **java.util.Properties**) hoặc YAML/JSON (thường cần thư viện, framework hoặc parser phù hợp).
- Environment variables, JVM system properties, tham số command line.
- Database hoặc dịch vụ cấu hình có kiểm soát nếu cần quản trị và phân phối tập trung.

Ví dụ file **app.properties**:

~~~properties
metrics.enabled=true
batch.max-jobs=5
~~~

Đây là **hai giá trị**, không phải tuyên bố rằng một method nào đó là metric hay một class nào đó đủ điều kiện batch. Một code path vẫn phải tải, parse, kiểm tra và áp dụng các giá trị đó.

### Các nguyên tắc vận hành

1. **Định nghĩa khóa, kiểu, default và khoảng hợp lệ.** Nếu cấu hình nói số batch tối đa bằng số âm, nên báo lỗi rõ ràng thay vì chấp nhận im lặng.
2. **Phân biệt thay file với áp dụng thay đổi.** Nếu app chỉ đọc config lúc khởi động, sửa file không làm giá trị đang nằm trong bộ nhớ tự đổi. Hot reload cần cơ chế riêng, cũng như cách cập nhật state an toàn.
3. **Quy định precedence.** Nếu cùng khóa xuất hiện trong file, environment và command line, tài liệu phải chỉ rõ nguồn nào thắng; Java **Properties** tự nó không áp đặt toàn bộ chính sách hợp nhất ấy cho ứng dụng.
4. **Đừng đưa secret vào source hoặc repository.** Secret cần kênh cấu hình/quản lý bí mật thích hợp, giới hạn quyền đọc và tránh log lộ dữ liệu.
5. **Không biến chuỗi cấu hình thành class name hoặc code chạy tùy ý.** Nếu cần chọn implementation, dùng danh sách lựa chọn cho phép hoặc registry rõ ràng, validate input và từ chối giá trị không được hỗ trợ.

Những yêu cầu như “có phải hành vi này được hỗ trợ ở type level?” cần interface; “phương thức nào phải thu thập metric?” cần metadata; “có bật thu thập metric hôm nay không?” cần config.

## 5. Ví dụ Java 17 chạy được: phối hợp cả ba

Tình huống: hệ thống có một job tạo báo cáo. Job có phương thức gắn metadata metric; kiểu job đủ điều kiện gửi vào batch; người vận hành quyết định có in thông tin metric và giới hạn batch qua file cấu hình.

Tạo **hai file cùng thư mục**.

**File app.properties:**

~~~properties
metrics.enabled=true
batch.max-jobs=5
~~~

**File DecisionDemo.java:**

~~~java
import java.io.Reader;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Measured {
    String value();
}

interface BatchEligible {
}

final class ReportJob implements BatchEligible {
    @Measured("monthly-report")
    public void run() {
        System.out.println("Running report");
    }
}

public class DecisionDemo {
    private static <T extends BatchEligible> void enqueue(T job) {
        System.out.println("Accepted batch job");
    }

    public static void main(String[] args) throws Exception {
        Properties config = new Properties();
        try (Reader reader = Files.newBufferedReader(
                Path.of("app.properties"), StandardCharsets.UTF_8)) {
            config.load(reader);
        }

        String rawEnabled = config.getProperty("metrics.enabled", "false")
                .trim().toLowerCase(Locale.ROOT);
        boolean metricsEnabled = switch (rawEnabled) {
            case "true" -> true;
            case "false" -> false;
            default -> throw new IllegalArgumentException(
                    "metrics.enabled must be true or false");
        };

        int maxJobs = Integer.parseInt(
                config.getProperty("batch.max-jobs", "1").trim());
        if (maxJobs < 1) {
            throw new IllegalArgumentException(
                    "batch.max-jobs must be >= 1");
        }

        ReportJob job = new ReportJob();
        Method runMethod = ReportJob.class.getMethod("run");
        Measured metadata = runMethod.getAnnotation(Measured.class);

        if (metricsEnabled && metadata != null) {
            System.out.println("Metric name: " + metadata.value());
        }

        System.out.println("Batch eligible: " +
                (job instanceof BatchEligible));

        if (job instanceof BatchEligible) {
            System.out.println("Batch size limit: " + maxJobs);
            enqueue(job);
        }

        job.run();
    }
}
~~~

Mở terminal tại thư mục chứa cả hai file và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DecisionDemo.java
java DecisionDemo
~~~

**Kết quả stdout đúng với file cấu hình ở trên:**

~~~text
Metric name: monthly-report
Batch eligible: true
Batch size limit: 5
Accepted batch job
Running report
~~~

**Đọc từng vai trò:**

- **@Measured("monthly-report")** lưu tên metric ngay trên phương thức **run()**. **@Retention(RUNTIME)** cho phép **getAnnotation** đọc được khi chương trình chạy. Chính nhánh **if (metricsEnabled && metadata != null)** mới quyết định có in dòng metric.
- **BatchEligible** là marker interface. **instanceof** kiểm tra ở runtime, còn chữ ký **<T extends BatchEligible>** của **enqueue** ràng buộc kiểu ở compile time. Không có logic retry, xếp lịch hay queue thật trong marker: phương thức **enqueue** ở đây chỉ minh họa việc chấp nhận job.
- **metrics.enabled** và **batch.max-jobs** đến từ **app.properties**. Code nạp file, chuyển kiểu và validate. Nếu đổi **metrics.enabled=false** rồi chạy lại chương trình, dòng **Metric name** không xuất hiện; marker và annotation trên source vẫn giữ nguyên. Nếu đổi **batch.max-jobs=8**, dòng **Batch size limit** hiển thị **8** sau lần chạy tiếp theo.

Ví dụ là chương trình console minh họa các điểm mở rộng, **chưa** phải một scheduler, metrics collector hay batch processor hoàn chỉnh. Trong hệ thống thật, consumer của annotation có thể thu thập metric, consumer của marker có thể đưa job vào bộ xử lý tương thích, và hệ thống cấu hình cấp giá trị giới hạn cho bộ xử lý.

### Vì sao không chỉ dùng một cơ chế?

- Chỉ có annotation với tên metric thì chưa thể quyết định **môi trường này có bật telemetry không**.
- Chỉ có file **metrics.enabled=true** thì chưa biết **method nào** thuộc danh sách cần gắn metric và gắn với tên nào, trừ khi xây một mapping bên ngoài có chủ ý.
- Chỉ có marker **BatchEligible** thì chưa có giá trị **batch.max-jobs**, cũng không biểu đạt metadata của riêng phương thức **run**.

Phân chia trách nhiệm làm hệ thống rõ nghĩa: **khai báo là gì**, **kiểu đủ điều kiện nào**, và **giá trị vận hành hiện tại bao nhiêu**.

## 6. So sánh các thiết kế thường dễ nhầm

### A. Annotation và marker interface đều “đánh dấu class”, chọn cái nào?

Giả sử thư viện xử lý tài liệu cần nhận loại đối tượng được phép đưa vào pipeline.

- API công khai muốn nhận **chỉ các kiểu được cho phép** ở thời điểm biên dịch, ví dụ **submit(T extends Exportable)**: marker **Exportable** là lựa chọn hợp lý (hoặc interface có method nếu có thao tác thực sự).
- Bộ framework muốn quét class, lấy tên format, version, hoặc thuộc tính khai báo của từng handler: annotation như **@DocumentHandler(format = "pdf")** phù hợp vì chứa metadata có cấu trúc.
- Nếu phải dùng reflection để phát hiện annotation class, cần chọn retention/runtime scan phù hợp. Nếu dùng marker và **instanceof**, thông tin kiểu có sẵn theo hợp đồng JVM. Hai kiểu consumer có kiến trúc khác nhau.

Không bắt buộc tạo cả marker lẫn annotation cho cùng một ý nghĩa. Chỉ kết hợp khi mỗi cái đảm nhận một trách nhiệm riêng có thể kiểm chứng.

### B. Cấu hình có thay được annotation không?

Có thể thiết kế mapping bên ngoài, ví dụ “method A → metric X” được nạp từ file. Cách đó phù hợp khi mapping phải thay đổi theo môi trường mà không build lại. Đổi lại cần định danh method ổn định, cơ chế kiểm tra mapping, xử lý rename/refactor và lỗi cấu hình. Với metadata là một phần của code contract, annotation gần khai báo thường dễ duy trì hơn.

Nếu điều cần đổi là **chính sách bật/tắt**, dùng config cho công tắc và annotation cho danh sách method sẽ rõ ràng. Không cần chuyển toàn bộ metadata sang config chỉ vì muốn có một công tắc.

### C. Annotation có thay interface chứa method được không?

Không hoàn toàn. Annotation có thể nói “lớp này là một handler”, nhưng Java compiler không tự bắt lớp đó cung cấp **handle()** chỉ vì annotation xuất hiện. Một annotation processor hoặc runtime validator có thể kiểm tra theo quy tắc do bạn cài đặt, nhưng đó là cơ chế bổ sung.

Nếu thuật toán cần gọi **handler.handle(request)** qua một hợp đồng polymorphism, hãy khai báo interface có method. Nếu hệ thống cần thêm thông tin như mã handler hay điều kiện đăng ký, có thể bổ sung annotation hoặc config.

### D. Marker interface khác gì boolean property trên object?

Một method **isBatchEligible()** có thể trả giá trị thay đổi theo từng object/trạng thái; marker interface phân loại theo kiểu class và không mang trạng thái. Nếu khả năng xử lý cần thay đổi theo instance hoặc theo runtime policy, một interface có phương thức, policy service hoặc config có thể diễn đạt chính xác hơn.

## 7. Cách ra quyết định khi thiết kế API

Hãy hỏi theo thứ tự:

1. **Người tiêu thụ cần gọi thao tác chung trên object không?** Nếu có, tạo interface có method hoặc abstraction thích hợp, thay vì marker rỗng.
2. **Thông tin cần được Java type system kiểm tra ở chữ ký/generic bound không?** Nếu có và chỉ cần thành viên một nhóm kiểu, xem xét marker interface.
3. **Thông tin thuộc về một class/method/field/parameter và cần processor/framework đọc không?** Nếu có, annotation có **@Target**, **@Retention** và consumer xác định là lựa chọn tự nhiên.
4. **Thông số/chính sách có thể thay đổi theo môi trường, vận hành hoặc deploy không?** Nếu có, đưa giá trị đó vào cấu hình bên ngoài, với default, validation và quy tắc reload rõ ràng.

Có thể nhiều câu trả lời là “có”. Khi ấy hãy tách các phần của yêu cầu, thay vì cố ép tất cả vào một phương tiện.

| Yêu cầu cụ thể | Lựa chọn khởi đầu hợp lý | Lý do |
| --- | --- | --- |
| Gắn tên metric cho từng method | Annotation | Metadata nằm ở mức phương thức |
| Chỉ cho phép đối tượng thuộc nhóm API nhất định vào một generic method | Marker interface | Type constraint được compiler kiểm tra |
| Đối tượng phải tự định nghĩa hành vi xử lý | Interface có method | Có hợp đồng thao tác để polymorphism hoạt động |
| Timeout khác nhau giữa môi trường | Cấu hình bên ngoài | Giá trị vận hành có thể đổi |
| Bật tracing production theo rollout | Cấu hình bên ngoài | Chính sách vận hành được điều chỉnh |
| Dùng @Test để test runner khám phá test | Annotation + test runner | Cần consumer thực thi quy ước annotation |
| Điều kiện đủ vào batch cố định theo kiểu, nhưng cỡ batch thay đổi | Marker + cấu hình | Phân loại kiểu và giới hạn vận hành tách biệt |
| Áp chính sách dựa trên vai trò người dùng thay đổi theo request | Policy/runtime authorization | Metadata tĩnh không tự thay thế kiểm tra bảo mật runtime |

## 8. Lỗi phổ biến và cách tránh

**Lỗi 1: Gắn annotation rồi kỳ vọng JVM tự chạy logic.** Một annotation tự viết chỉ là metadata. Phải chỉ ra annotation processor, reflection scanner, interceptor hay framework nào sẽ xử lý nó; đồng thời viết kiểm thử đường đi thực thi đó.

**Lỗi 2: Dùng marker interface vì “trông giống thiết kế OOP” nhưng chẳng code nào kiểm tra nó.** Marker không có phép màu. Nếu không có API nhận marker, type bound hoặc runtime consumer, nó chỉ tăng thêm một tên kiểu và quan hệ implements.

**Lỗi 3: Dùng annotation để giả lập hợp đồng method.** Khi client cần gọi hành vi chung, dùng interface có method để compiler bảo đảm phương thức tồn tại. Annotation có thể bổ sung metadata cho hợp đồng đó.

**Lỗi 4: Đưa tham số thay đổi theo môi trường vào annotation hoặc source constant.** Thay đổi chúng thường yêu cầu build mới. Tách phần metadata ổn định khỏi config vận hành.

**Lỗi 5: Nghĩ thay config file có hiệu lực tức thì.** App chỉ nạp khi khởi động sẽ giữ giá trị cũ cho tới khi nạp lại/restart. Với hot reload, cần định nghĩa thời điểm và tính nhất quán của cập nhật.

**Lỗi 6: Đọc config mà không validate.** Boolean bị gõ sai, số âm, timeout quá lớn, hoặc tên implementation không hợp lệ có thể làm hệ thống chạy sai. Parse chặt chẽ, từ chối giá trị ngoài miền, báo rõ khóa lỗi và dùng default có chủ ý.

**Lỗi 7: Trộn “đủ điều kiện” với “được phép thực thi”.** Marker hay annotation có thể mô tả đặc tính kỹ thuật, nhưng quyết định ủy quyền dựa trên người dùng, resource và context phải được kiểm tra ở runtime. Không dùng marker/annotation tĩnh như một hệ thống phân quyền hoàn chỉnh.

**Lỗi 8: Lạm dụng retention RUNTIME và reflection khi không cần.** Nếu chỉ muốn compile-time warning, annotation processor hoặc compiler check có thể đủ; nếu yêu cầu compile-time type bound, marker/interface thích hợp hơn. Reflection còn cần quy tắc scan, phạm vi và xử lý lỗi rõ ràng.

## 9. Bài tập tự kiểm tra

Thử chọn giải pháp trước khi đọc phần gợi ý:

1. Cần đánh dấu 20 phương thức để test engine tìm và chạy.
2. Thư viện chỉ nhận object có một “dấu” khả năng tương thích và muốn chặn kiểu không hợp lệ từ compile time.
3. Hệ thống cần chỉnh số lần retry theo dev/staging/prod.
4. Mỗi chiến lược thanh toán phải thực thi phương thức **pay()**.
5. Mỗi phương thức xử lý message có tên topic cố định; việc bật/tắt consumer được quyết định bởi môi trường.

**Gợi ý:** (1) annotation có test runner; (2) marker interface nếu hợp đồng thực sự là phân loại kiểu; (3) config; (4) interface có method; (5) annotation cho topic metadata và config cho trạng thái bật/tắt, cùng một consumer/framework xử lý cả hai.

Điểm cần giữ khi tự thiết kế: xác định **consumer** trước. Biết ai sẽ đọc marker/annotation/config, lúc nào đọc, kiểm tra được điều gì và hậu quả khi thiếu/sai giá trị, thì việc chọn cơ chế Java sẽ rõ ràng hơn.