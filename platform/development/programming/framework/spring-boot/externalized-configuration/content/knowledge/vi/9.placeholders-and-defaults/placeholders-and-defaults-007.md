# Phân biệt placeholder ${...} với biểu thức SpEL #{...} trong Spring Boot

## Mục tiêu

Trong Spring Boot, hai cú pháp **${...}** và **#{...}** thường xuất hiện gần nhau trong annotation **@Value**, file cấu hình và các ví dụ về dependency injection. Chúng có cùng điểm chung là giúp một thành phần nhận giá trị khi ứng dụng khởi tạo, nhưng chúng giải quyết **hai bài toán khác nhau**:

- **Property placeholder — ${...}:** tìm một khóa cấu hình trong Spring Environment, có thể dùng một giá trị mặc định khi khóa không được giải quyết.
- **Spring Expression Language (SpEL) — #{...}:** đánh giá một biểu thức trong ngữ cảnh Spring, chẳng hạn tính toán số học, lựa chọn bằng điều kiện, đọc thuộc tính của một bean hoặc gọi phương thức được cho phép.

Ví dụ:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("#{10 * 2}")
private int doubleTen;
~~~

Dòng đầu hỏi **“Spring đang có giá trị cấu hình server.port nào?”**. Dòng thứ hai hỏi **“Biểu thức 10 * 2 tính được bao nhiêu?”**. Nếu chưa phân biệt được hai câu hỏi này, một đoạn mã dễ dùng SpEL để giải quyết vấn đề cấu hình, hoặc lầm tưởng rằng chuỗi SpEL trong application.yml luôn được Spring Boot tính toán tự động.

Sau bài học, người đọc có thể nhận diện chính xác hai cú pháp, hiểu giá trị mặc định của placeholder, biết thứ tự xử lý khi phối hợp hai cơ chế và chọn cách khai báo phù hợp khi triển khai ứng dụng.

## 1. Hai cú pháp khác nhau ở đâu?

| Tiêu chí | Property placeholder ${...} | SpEL #{...} |
| --- | --- | --- |
| Mục đích chính | Tra cứu thuộc tính cấu hình | Đánh giá một biểu thức |
| Ví dụ đơn giản | ${app.name:demo} | #{3 + 7} |
| Đầu vào chính | Các PropertySource của Spring Environment | Ngữ cảnh đánh giá biểu thức của Spring |
| Cách lấy giá trị | Tìm khóa **app.name** | Tính phép cộng **3 + 7** |
| Giá trị mặc định | Thường dùng **:**: ${app.name:demo} | Dùng toán tử biểu thức, ví dụ **?:** |
| Kiểu kết quả | Giá trị thuộc tính, thường bắt đầu ở dạng chuỗi, có thể chuyển kiểu khi inject | Có thể là số, boolean, String, đối tượng, tập hợp... |
| Truy cập bean khác | Không phải chức năng chính | Có thể dùng **@beanName** trong ngữ cảnh phù hợp |
| Đặc điểm quan trọng | Tuân theo thứ tự ưu tiên nguồn cấu hình | Có khả năng tính toán, truy cập dữ liệu và gọi phương thức |
| Khuyến nghị | Dùng cho cấu hình môi trường và giá trị có thể thay đổi khi triển khai | Dùng khi cần một biểu thức thực sự, đơn giản và được kiểm soát |

**Cần phân biệt cú pháp của Spring với cú pháp Java:** trong mã Java, phần **"${...}"** là nội dung của một chuỗi ký tự truyền cho annotation; bản thân Java không xử lý placeholder. Spring thực hiện bước phân giải khi tạo bean. Tương tự, **"#{...}"** không phải cú pháp toán học của Java: nó được Spring nhận diện và xử lý như một biểu thức.

Không phải mọi nơi chứa chuỗi ${...} hoặc #{...} đều tự động chạy cả hai cơ chế. Chúng chỉ có ý nghĩa đặc biệt ở những điểm tích hợp Spring hỗ trợ phân giải placeholder hoặc SpEL.

## 2. Property placeholder ${...}: tìm giá trị trong Environment

Giả sử application.yml có:

~~~yaml
app:
  display-name: "Inventory Service"
  worker:
    threads: 8
    enabled: true
~~~

Trong một bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WorkerInfo {

    @Value("${app.display-name}")
    private String name;

    @Value("${app.worker.threads}")
    private int threads;

    @Value("${app.worker.enabled}")
    private boolean enabled;

    public String description() {
        return name + ": " + threads + " threads, enabled=" + enabled;
    }
}
~~~

Spring giải quyết ba placeholder từ thuộc tính đã nạp vào Environment. Trong ví dụ cơ sở, lần lượt nhận được **Inventory Service**, **8** và **true**. Với hai trường int và boolean, Spring còn chuyển giá trị cấu hình sang kiểu đích.

**Không phải tên field quyết định tên property được tìm.** Ví dụ field Java **threads** không tự động là khóa **app.worker.threads** trong một annotation @Value; chính nội dung placeholder đã chỉ định khóa.

### 2.1. Giá trị có thể đến từ nhiều nguồn

Giữ application.yml như trên, chạy:

~~~bash
APP_WORKER_THREADS=12 java -jar inventory.jar
~~~

Nếu không có nguồn cấu hình khác ưu tiên cao hơn, biến môi trường **APP_WORKER_THREADS** có thể ghi đè giá trị **8** trong file. Placeholder **${app.worker.threads}** sau đó giải quyết được giá trị **12**.

Tiếp tục chạy:

~~~bash
APP_WORKER_THREADS=12 java -Dapp.worker.threads=14 -jar inventory.jar   --app.worker.threads=16
~~~

Trong thứ tự PropertySource thông thường giữa các nguồn này, tham số dòng lệnh **--app.worker.threads=16** được ưu tiên hơn JVM system property **14**, biến môi trường **12** và file YAML **8**.

Khi viết:

~~~java
@Value("${app.worker.threads}")
private int threads;
~~~

Spring sử dụng kết quả phân giải cấu hình theo precedence, thay vì chỉ đọc trực tiếp một biến môi trường cụ thể.

### 2.2. Tra cứu bằng Environment

Một mã tương đương về mục tiêu tra cứu cấu hình:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigReader {
    private final Environment environment;

    ConfigReader(Environment environment) {
        this.environment = environment;
    }

    String name() {
        return environment.getProperty("app.display-name", "Unknown");
    }

    int threads() {
        return environment.getProperty("app.worker.threads", Integer.class, 4);
    }
}
~~~

Trong trường hợp này, **Environment.getProperty(...)** đọc từ các PropertySource. Nó không đồng nghĩa với việc đánh giá một biểu thức SpEL tùy ý. Nếu có một chuỗi trông như **#{1 + 2}** trong nguồn cấu hình, API getProperty thông thường không vì thế tự động chạy nó như phép toán.

## 3. Giá trị mặc định của placeholder: dấu hai chấm

Cú pháp thường gặp:

~~~text
${property.name:default-value}
~~~

Ví dụ:

~~~java
@Value("${app.worker.threads:4}")
private int threads;

@Value("${app.display-name:Demo Service}")
private String displayName;

@Value("${app.feature.enabled:false}")
private boolean enabled;
~~~

Nếu ứng dụng **không giải quyết được** app.worker.threads từ các nguồn cấu hình, placeholder dùng chuỗi mặc định **4**, sau đó Spring chuyển thành int để inject. Tương tự, displayName có mặc định **Demo Service**, enabled có mặc định **false**.

Dấu hai chấm thuộc cú pháp của property placeholder; nó không có nghĩa toán tử ba ngôi của Java.

### 3.1. Mặc định chỉ là phương án khi không tìm được giá trị

Xem ba tình huống:

~~~properties
# Tình huống A: khóa không tồn tại

# Tình huống B: khóa có mặt nhưng rỗng
app.display-name=

# Tình huống C: khóa có giá trị cụ thể
app.display-name=Order Service
~~~

Annotation:

~~~java
@Value("${app.display-name:Unnamed}")
private String displayName;
~~~

Trong tình huống thường gặp:

| Tình huống | Kết quả |
| --- | --- |
| Không có app.display-name trong các nguồn | **Unnamed** |
| Có app.display-name với chuỗi rỗng | **""** (chuỗi rỗng) |
| Có app.display-name=Order Service | **Order Service** |

Điều này giải thích một hiểu nhầm phổ biến: phần mặc định sau dấu **:** không có nghĩa “thay bất cứ giá trị falsy nào”. Chuỗi rỗng **đã được tìm thấy** có thể vẫn là một giá trị hợp lệ, tùy cách PropertySource cung cấp dữ liệu.

Nếu nghiệp vụ không chấp nhận chuỗi rỗng, hãy khai báo yêu cầu rõ ràng bằng validation hoặc xử lý nghiệp vụ, thay vì mặc định cho rằng placeholder sẽ thay nó.

### 3.2. Mặc định rỗng

Ví dụ:

~~~java
@Value("${app.optional-label:}")
private String label;
~~~

Ở đây phần sau dấu **:** là chuỗi rỗng. Nếu không có app.optional-label, label có thể là **""**.

Đây là lựa chọn hợp lý cho trường chuỗi thực sự tùy chọn. Nhưng nếu field là int:

~~~java
@Value("${app.worker.threads:}")
private int threads;
~~~

thì default rỗng có thể không chuyển đổi được sang int nguyên thủy. Nên dùng số hợp lệ, kiểu có thể vắng mặt hoặc cơ chế cấu hình có validation phù hợp.

### 3.3. Placeholder lồng nhau

Spring hỗ trợ các placeholder tham chiếu lẫn nhau ở các điểm phân giải phù hợp:

~~~properties
app.base-url=https://api.example.test
app.health-url=${app.base-url}/health
~~~

Sau khi được phân giải, app.health-url có thể trở thành **https://api.example.test/health**.

Một mẫu fallback khác:

~~~java
@Value("${app.display-name:${spring.application.name:Demo}}")
private String displayName;
~~~

Ý tưởng:

1. Tìm app.display-name.
2. Nếu không có, tìm spring.application.name.
3. Nếu cả hai đều không có, dùng Demo.

Các placeholder có thể trở nên khó đọc nếu lồng quá sâu. Với cấu hình phức tạp, nên đặt default hợp lý trong file hoặc lớp @ConfigurationProperties và giữ việc tra cứu đơn giản.

### 3.4. Ký tự hai chấm trong giá trị mặc định

Ví dụ:

~~~java
@Value("${app.callback-url:https://example.test/callback}")
private String callbackUrl;
~~~

Phần mặc định có thể là một URL chứa dấu **:**. Bộ phân giải xác định dấu phân cách mặc định theo cú pháp placeholder, chứ không đơn giản tách mọi dấu hai chấm trong URL.

Tuy nhiên, với các giá trị phức tạp có nhiều ký tự đặc biệt, hãy chú ý cách Java, YAML, .properties và shell của môi trường triển khai xử lý dấu nháy và escape. Không suy diễn mọi ngữ cảnh đều parse giống nhau.

## 4. SpEL #{...}: đánh giá biểu thức

**Spring Expression Language**, viết tắt **SpEL**, là ngôn ngữ biểu thức được Spring cung cấp để mô tả phép tính, logic, truy cập thuộc tính, truy cập bean và các thao tác khác trong một ngữ cảnh đánh giá phù hợp.

Những ví dụ cơ bản:

~~~java
@Value("#{4 + 6}")
private int ten;

@Value("#{'hello'.toUpperCase()}")
private String upperGreeting;

@Value("#{10 > 3}")
private boolean bigger;

@Value("#{T(java.lang.Math).max(7, 12)}")
private int maximum;
~~~

SpEL hiểu cú pháp toán học, literal String, phép so sánh, gọi phương thức và tham chiếu kiểu **T(...)**. Các biểu thức lần lượt cho kết quả **10**, **HELLO**, **true** và **12** khi được đánh giá trong ngữ cảnh hỗ trợ.

Điểm khác với placeholder: trong **#{4 + 6}**, **4 + 6 là biểu thức cần tính**, không phải một tên thuộc tính cấu hình. Nếu viết **${4 + 6}**, Spring sẽ cố hiểu nội dung như tên placeholder, không tự chuyển sang thực hiện phép cộng SpEL.

### 4.1. SpEL làm phép tính và so sánh

~~~java
@Value("#{3 * (4 + 2)}")
private int capacity;

@Value("#{15 >= 10}")
private boolean acceptable;

@Value("#{('A' + 'B') == 'AB'}")
private boolean sameText;
~~~

Một số toán tử được dùng phổ biến trong SpEL: **+**, **-**, *****, **/**, **%**, **>**, **<**, **>=**, **<=**, **==**, **!=**, các toán tử logic và phép so sánh phù hợp.

Các phép tính phải phù hợp với kiểu giá trị. Ví dụ một String chứa chữ **"five"** không tự biến thành số nguyên 5 chỉ vì được đưa vào phép nhân.

### 4.2. SpEL có điều kiện

Ví dụ toán tử ba ngôi:

~~~java
@Value("#{8 > 5 ? 'large' : 'small'}")
private String category;
~~~

Vì 8 > 5, kết quả là **large**.

Ví dụ toán tử Elvis trong SpEL:

~~~java
@Value("#{'dev' ?: 'default'}")
private String profileLabel;
~~~

Toán tử **?:** chọn giá trị phía sau khi phía trước có giá trị null hoặc trường hợp rỗng được SpEL xử lý theo quy tắc Elvis. Đây là phép kiểm tra trong biểu thức, khác với dấu hai chấm trong **${app.name:default}**.

Cần phân biệt ba cú pháp:

~~~text
${app.name:Guest}               // default của property placeholder
#{flag ? 'yes' : 'no'}       // toán tử điều kiện SpEL
#{name ?: 'Guest'}           // toán tử Elvis SpEL
~~~

Trong ví dụ SpEL, **flag** và **name** phải là đối tượng/biến có thể được giải quyết trong ngữ cảnh đánh giá thực tế. Không thể lấy hai tên đó đặt vào @Value bất kỳ rồi giả định chúng đã được khai báo. Các snippet này minh họa cú pháp toán tử.

### 4.3. SpEL truy cập thuộc tính Java và bean

Giả sử có bean:

~~~java
import org.springframework.stereotype.Component;

@Component("quotaSettings")
public class QuotaSettings {

    public int getDailyLimit() {
        return 100;
    }
}
~~~

Bean khác có thể dùng:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class QuotaInfo {

    @Value("#{@quotaSettings.dailyLimit}")
    private int dailyLimit;
}
~~~

Trong SpEL, **@quotaSettings** biểu diễn tham chiếu tới bean đã được đăng ký tên quotaSettings; **dailyLimit** được đọc thông qua thuộc tính JavaBean/getter tương ứng trong trường hợp này.

Đây là tính năng SpEL mà property placeholder không nhằm cung cấp: **${quotaSettings.dailyLimit}** có ý nghĩa tìm một **khóa cấu hình**, không tự động lấy getter từ bean quotaSettings.

Dù SpEL truy cập bean rất linh hoạt, việc tham chiếu chéo tùy ý có thể làm phụ thuộc giữa các bean khó quản lý, ảnh hưởng thứ tự khởi tạo và gây vòng phụ thuộc. Nếu một class cần dữ liệu từ bean khác, constructor injection thường diễn đạt quan hệ rõ ràng hơn.

### 4.4. SpEL truy cập system properties

Ví dụ:

~~~java
@Value("#{systemProperties['java.version']}")
private String javaVersion;
~~~

Trong ngữ cảnh đánh giá @Value của Spring, **systemProperties** cho phép tham chiếu đến các Java system properties theo cơ chế tích hợp của Spring.

Không nên nhầm:

~~~java
@Value("${java.version}")
private String javaVersionFromEnvironment;
~~~

Cách thứ hai tìm **java.version** như một property placeholder trong Spring Environment. Hai ví dụ có thể nhận cùng một giá trị ở trường hợp nhất định, nhưng đường đi và ngữ nghĩa khác nhau.

## 5. Ví dụ đối chiếu trực tiếp

Hãy đặt cạnh nhau ba annotation:

~~~java
@Value("${app.max-items:10}")
private int configuredLimit;

@Value("#{10 * 2}")
private int constantCalculation;

@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;
~~~

Kết quả:

| Annotation | Spring xử lý điều gì? | Kết quả minh họa |
| --- | --- | --- |
| ${app.max-items:10} | Tra cứu app.max-items, nếu không có dùng 10 | Phụ thuộc cấu hình, có thể 10 hoặc giá trị override |
| #{10 * 2} | Tính 10 nhân 2 | 20 |
| #{T(java.lang.Math).max(10, 20)} | Gọi phương thức Math.max trong ngữ cảnh SpEL | 20 |

Thay đổi một biến môi trường như **APP_MAXITEMS=40** có thể thay **configuredLimit**, nhưng không tự thay phép toán hằng **10 * 2** hay hai đối số của Math.max trong các biểu thức còn lại.

Đây là tiêu chí chọn cú pháp:

- Nếu người vận hành cần thay giá trị theo dev/test/prod mà không sửa mã: **placeholder** hoặc **@ConfigurationProperties**.
- Nếu cần một phép tính, phép chọn nhánh hoặc truy cập có chủ đích đến một đối tượng trong ngữ cảnh Spring: **SpEL**.
- Nếu logic đủ phức tạp để cần nhiều bước, kiểm tra điều kiện, logging hoặc test: nên đưa nó vào mã Java thông thường thay vì nhồi trong @Value.

## 6. Kết hợp placeholder và SpEL trong cùng @Value

Một trường hợp quan trọng là **phân giải placeholder trước, rồi đánh giá biểu thức** ở điểm tích hợp @Value do Spring quản lý.

Giả sử:

~~~properties
app.batch-size=16
~~~

Ta muốn tính dung lượng gấp đôi:

~~~java
@Value("#{${app.batch-size:8} * 2}")
private int bufferCapacity;
~~~

Ở cấu hình minh họa này:

1. Bộ phân giải placeholder tìm **app.batch-size**.
2. Nếu tìm thấy **16**, chuỗi biểu thức sau phân giải tương ứng với **#{16 * 2}**.
3. SpEL tính phép nhân.
4. Kết quả **32** được inject vào field int.

Nếu app.batch-size không tồn tại, mặc định **8** được dùng; biểu thức được tính với 8, cho kết quả **16**.

Điểm quan trọng: dấu **${...}** giải quyết **đầu vào cấu hình**; dấu **#{...}** giải quyết **biểu thức tính toán**. Hai cơ chế không trở thành một chỉ vì chúng nằm cùng chuỗi annotation.

### 6.1. Ví dụ kết hợp điều kiện

Giả sử:

~~~properties
app.worker-count=6
~~~

Annotation:

~~~java
@Value("#{${app.worker-count:2} > 4 ? 'large' : 'small'}")
private String sizeLabel;
~~~

Giá trị cấu hình **6** được thay vào biểu thức rồi so sánh với 4, cho kết quả **large**. Nếu property bị thiếu, biểu thức sử dụng số mặc định 2 và nhận **small**.

Đây là ví dụ tốt để hiểu trình tự xử lý, nhưng trong mã nghiệp vụ dài hạn có thể rõ ràng hơn khi bind workerCount thành một trường kiểu int rồi viết:

~~~java
String sizeLabel = workerCount > 4 ? "large" : "small";
~~~

Cách này tránh biến một annotation thành nơi chứa logic nghiệp vụ.

### 6.2. Khi giá trị lấy từ property là chuỗi

Với số nguyên thuần như 16, mẫu **#{${app.batch-size:8} * 2}** tương đối dễ hiểu. Với String, không thể luôn thay trực tiếp chuỗi vào biểu thức mà không xét dấu nháy và ký tự đặc biệt.

Ví dụ một giá trị cấu hình chứa dấu cách, dấu nháy hoặc ký tự có ý nghĩa trong SpEL có thể khiến biểu thức lỗi cú pháp, thay đổi nghĩa hoặc tạo rủi ro nếu nguồn dữ liệu không đáng tin cậy. Không nên tạo SpEL bằng cách nội suy trực tiếp dữ liệu tùy ý của người dùng vào mã biểu thức.

Khi cần tính toán dựa trên một String tùy biến, ưu tiên đọc String qua @ConfigurationProperties rồi xử lý bằng Java. Nếu một biểu thức là thật sự cần thiết, phải kiểm soát kiểu dữ liệu và ngữ cảnh đánh giá của nó.

### 6.3. Khi kết hợp quá nhiều tầng mặc định

Một annotation có thể nhanh chóng trở nên khó hiểu nếu vừa có placeholder lồng nhau, vừa có SpEL, vừa chuyển kiểu. Ví dụ dạng khó đọc:

~~~text
#{ ... ${first:${second:10}} ... ? ... : ... }
~~~

Trong ứng dụng dài hạn, tốt hơn nên tách:

1. Quyết định giá trị cấu hình và mặc định tại lớp cấu hình.
2. Kiểm tra tính hợp lệ ở lúc khởi động.
3. Tính toán hoặc lựa chọn theo nghiệp vụ trong một phương thức Java.

Cách này giúp thông báo lỗi nêu rõ khóa cấu hình nào sai và giảm độ phụ thuộc vào cú pháp biểu thức.

## 7. @Value và @ConfigurationProperties: khác nhau khi xử lý biểu thức

Trong Spring Boot, **@Value** phù hợp để inject một vài giá trị, còn **@ConfigurationProperties** được thiết kế để bind một nhóm thuộc tính có cấu trúc và có khả năng relaxed binding, chuyển đổi kiểu, validation.

Ví dụ nhóm cấu hình:

~~~yaml
app:
  worker:
    threads: 8
    queue-capacity: 120
    enabled: true
~~~

Một record cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        int queueCapacity,
        boolean enabled
) {
}
~~~

Khi được đăng ký, Spring Boot bind các khóa vào WorkerProperties, không cần ba annotation @Value.

**Phân biệt then chốt:** binding của **@ConfigurationProperties** không sử dụng SpEL để tự đánh giá các chuỗi cấu hình như **#{1 + 2}**. Ví dụ:

~~~yaml
app:
  worker:
    threads: "#{4 + 4}"
~~~

Đây là chuỗi cấu hình có hình thức SpEL, nhưng binder không mặc nhiên tính thành số 8 để gán vào int. Kết quả có thể là lỗi chuyển kiểu vì chuỗi không phải số hợp lệ. Không dùng cách viết này để thiết kế cấu hình @ConfigurationProperties.

Ngược lại, @Value hỗ trợ diễn giải SpEL tại điểm inject:

~~~java
@Value("#{4 + 4}")
private int threads;
~~~

Kết quả trong trường hợp này là 8.

### 7.1. Cách có mặc định rõ ràng với ConfigurationProperties

Một cách thiết kế là cung cấp mặc định qua file nền:

~~~yaml
app:
  worker:
    threads: 4
    queue-capacity: 100
    enabled: true
~~~

Các môi trường có thể override qua file theo profile hoặc biến môi trường. Nếu thuộc tính bắt buộc, sử dụng validation khi bind:

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @Min(1) int queueCapacity,
        boolean enabled
) {
}
~~~

Để validation hoạt động cần dependency và cấu hình Jakarta Bean Validation phù hợp. Ý nghĩa ở đây là **tách giá trị cấu hình khỏi logic tính toán**, đồng thời phát hiện cấu hình không hợp lệ sớm.

### 7.2. Canonical name trong @Value

Khi dùng placeholder @Value, nên ghi tên thuộc tính dạng canonical **chữ thường, kebab-case**, ví dụ:

~~~java
@Value("${app.worker.queue-capacity:100}")
private int queueCapacity;
~~~

Cách đặt này giúp cơ chế tra cứu cấu hình của Spring Boot liên kết tốt hơn với các biến thể tên ở nguồn như biến môi trường **APP_WORKER_QUEUECAPACITY**.

Viết:

~~~java
@Value("${app.worker.queueCapacity:100}")
private int queueCapacity;
~~~

có thể tạo hành vi tra cứu khác trong một số nguồn. Không nên xem mọi tên camelCase trong placeholder tương đương tuyệt đối với canonical kebab-case. Trong một lớp có nhiều property, @ConfigurationProperties thường giảm những rủi ro kiểu đặt tên này.

## 8. Trong application.yml và application.properties: cú pháp nào được xử lý?

Một file YAML là nguồn dữ liệu. Việc YAML chứa chuỗi có dấu **${...}** hoặc **#{...}** không làm toàn bộ file trở thành mã biểu thức chạy tức thì.

Ví dụ:

~~~yaml
app:
  name: "Payment Service"
  banner: "Service: ${app.name}"
  arithmetic-text: "#{10 * 2}"
~~~

Giải thích theo từng tầng:

- **app.name** là một chuỗi bình thường.
- **app.banner** chứa placeholder tham chiếu property khác; ở các điểm Spring phân giải placeholder, nó có thể tạo chuỗi **Service: Payment Service**.
- **app.arithmetic-text** chứa văn bản có hình thức SpEL. Spring Boot không mặc nhiên đánh giá mọi scalar trong YAML thành biểu thức. Nếu dùng @ConfigurationProperties để bind vào String, giá trị này có thể vẫn là chuỗi **#{10 * 2}**.

Trong khi đó, nếu dùng @Value:

~~~java
@Value("${app.arithmetic-text}")
private int result;
~~~

đường đi có thể khác vì @Value hỗ trợ cả bước phân giải placeholder và đánh giá biểu thức; chuỗi được lấy từ property có thể được bộ xử lý biểu thức ở điểm inject diễn giải thành kết quả. Điều đó không biến **application.yml** thành ngôn ngữ SpEL toàn cục và không đảm bảo behavior tương tự qua mọi API đọc cấu hình.

**Cách tổ chức rõ ràng:** lưu **dữ liệu cấu hình** trong YAML/properties; chỉ viết SpEL tại những vị trí hỗ trợ biểu thức và thực sự cần đánh giá.

### 8.1. Dấu # trong YAML

Trong YAML, dấu **#** có thể mở đầu comment khi nằm ở vị trí hợp lệ. Vì vậy một giá trị chứa chuỗi **#{...}** nên được quote rõ ràng:

~~~yaml
app:
  expression-example: "#{10 * 2}"
~~~

Tương tự, với các scalar chứa dấu **:**, dấu ngoặc hoặc ký tự đặc biệt, dùng dấu nháy phù hợp để parser YAML giữ đúng chuỗi. Tuy nhiên quote trong YAML chỉ điều khiển **cú pháp YAML**, không tự quyết định Spring phải đánh giá SpEL.

### 8.2. Dấu nháy trong properties khác YAML

Trong YAML:

~~~yaml
app:
  label: "Hello"
~~~

dấu nháy delimiting string không phải một phần giá trị.

Trong .properties:

~~~properties
app.label="Hello"
~~~

dấu nháy thường là ký tự trong giá trị theo cú pháp Java properties; không tự có ý nghĩa giống YAML. Vì vậy khi khai báo placeholder hoặc SpEL dưới dạng giá trị file .properties, hãy chú ý rằng dấu nháy có thể là dữ liệu thực, làm biểu thức khác đi.

Ví dụ phổ biến hơn, đơn giản hơn:

~~~properties
app.label=Hello
app.banner=Service: ${app.label}
~~~

Những giá trị này có thể được phân giải placeholder khi được Spring Environment xử lý trong ngữ cảnh hỗ trợ.

## 9. Khác biệt giữa placeholder và SpEL khi không tìm thấy giá trị

Giả sử file cấu hình **không chứa** khóa app.retry-count.

Với placeholder không có default:

~~~java
@Value("${app.retry-count}")
private int retries;
~~~

Trong cấu hình @Value thông thường được Spring Boot quản lý, thiếu property có thể khiến quá trình khởi tạo bean thất bại với lỗi kiểu **Could not resolve placeholder** hoặc một lỗi lồng bên trong bean creation exception. Không nên giả định Spring luôn inject null.

Với default:

~~~java
@Value("${app.retry-count:3}")
private int retries;
~~~

giá trị **3** có thể được sử dụng. Nếu property tồn tại nhưng có giá trị **abc**, việc chuyển sang int có thể thất bại; default không thay thế một giá trị đã được tìm thấy nhưng không hợp lệ.

SpEL lại có cách xử lý khác. Ví dụ:

~~~java
@Value("#{null}")
private String name;
~~~

SpEL đánh giá literal null rồi Spring xử lý giá trị đích phù hợp. Đây **không phải** trường hợp “placeholder không tồn tại”.

Với toán tử điều kiện:

~~~java
@Value("#{null ?: 'Guest'}")
private String name;
~~~

SpEL đánh giá null, sau đó toán tử Elvis chọn **Guest**. Không có bước tra cứu khóa cấu hình nào trong biểu thức này.

Bảng so sánh:

| Trường hợp | Placeholder | SpEL |
| --- | --- | --- |
| Thiếu property | Có thể lỗi nếu không có mặc định | Không áp dụng trực tiếp nếu biểu thức không đọc property |
| Có mặc định | ${app.name:Guest} | #{null ?: 'Guest'} |
| Sai kiểu khi inject | Có thể lỗi chuyển kiểu sau khi tra cứu | Có thể lỗi đánh giá hoặc chuyển kiểu kết quả |
| Cần một bean khác | Không được thiết kế để truy cập bean qua tên property | Có thể dùng tham chiếu bean @name |
| Tham chiếu đến khóa cấu hình | Chức năng chính | Cần truy cập Environment hoặc kết hợp với placeholder |

## 10. Những trường hợp cần phân biệt null, rỗng và vắng mặt

Với các nguồn cấu hình, giá trị **không tồn tại**, **chuỗi rỗng** và **null** không phải ba cách viết đồng nghĩa.

Ví dụ YAML:

~~~yaml
app:
  label-empty: ""
  label-null: null
  label-literal: "null"
~~~

Trong YAML, **""** là chuỗi rỗng; **null** là null scalar; **"null"** là chuỗi văn bản gồm bốn ký tự. Khi đưa vào Spring Environment, cách xử lý null phụ thuộc bộ nạp dữ liệu và cơ chế giải quyết PropertySource.

Với annotation:

~~~java
@Value("${app.label-empty:Fallback}")
private String label;
~~~

nếu nguồn chứa chuỗi rỗng, default **Fallback** thường không được chọn chỉ vì chuỗi có độ dài 0.

Với SpEL Elvis:

~~~java
@Value("#{' ' ?: 'Fallback'}")
private String labelWithSpace;
~~~

Một chuỗi chỉ gồm dấu cách không nhất thiết bị coi là chuỗi rỗng; phải xét quy tắc Elvis của SpEL và giá trị cụ thể.

**Không dùng null của YAML như cơ chế chắc chắn để xóa giá trị của một nguồn cấu hình ưu tiên thấp hơn.** Nếu muốn tắt một tính năng, dùng một property có nghĩa rõ:

~~~yaml
app:
  notifications:
    enabled: false
~~~

Với giá trị bắt buộc, dùng validation thích hợp thay vì lạm dụng SpEL để vá những input chưa được quy định.

## 11. SpEL có thể truy cập bean và có tác động phụ

Khác với placeholder chỉ tra cứu tên thuộc tính, SpEL có khả năng đi qua đối tượng và gọi phương thức nếu evaluation context cho phép.

Ví dụ:

~~~java
@Value("#{@quotaSettings.dailyLimit}")
private int limit;
~~~

Nếu quotaSettings có getter thuần, việc đọc thuộc tính tương đối dễ dự đoán. Nhưng nếu biểu thức gọi phương thức làm thay đổi trạng thái, truy vấn database hoặc gọi service ngoài, quá trình tạo bean có thể gây tác động phụ khó phát hiện.

Đặc biệt, đừng đưa vào SpEL các chuỗi tự do từ request HTTP, input của người dùng hoặc nguồn cấu hình không tin cậy rồi đánh giá như mã. **SpEL là một ngôn ngữ biểu thức có khả năng thực thi**, không phải một bộ đọc chuỗi vô hại.

Một số nguyên tắc sử dụng:

1. Viết biểu thức ngắn và dùng nguồn dữ liệu đáng tin cậy.
2. Không biến các giá trị cấu hình của người dùng thành một biểu thức SpEL mới để đánh giá.
3. Nếu cần tham chiếu bean, cân nhắc constructor injection thay vì phụ thuộc ngầm qua chuỗi biểu thức.
4. Tránh phương thức gây side effect trong các biểu thức phục vụ khởi tạo cấu hình.
5. Với dữ liệu phức tạp, bind qua @ConfigurationProperties rồi xử lý bằng Java.

Đây là khác biệt về **khả năng và phạm vi áp dụng**, không phải một yêu cầu phải dùng SpEL mỗi khi cần giá trị động.

## 12. Khi nào cần dùng SpEL thay vì tính toán bằng Java?

Giả sử ứng dụng có cấu hình:

~~~yaml
app:
  concurrency:
    workers: 6
    tasks-per-worker: 10
~~~

Một cách giải quyết bằng annotation:

~~~java
@Value("#{${app.concurrency.workers:4} * ${app.concurrency.tasks-per-worker:8}}")
private int totalTaskCapacity;
~~~

Spring phân giải hai placeholder trước khi SpEL tính phép nhân. Với hai giá trị 6 và 10, kết quả là 60.

Tuy nhiên, nếu totalTaskCapacity là logic quan trọng trong ứng dụng, giải pháp dễ test và dễ debug hơn là:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.concurrency")
public record ConcurrencyProperties(int workers, int tasksPerWorker) {

    public int totalTaskCapacity() {
        return workers * tasksPerWorker;
    }
}
~~~

Đặt giá trị mặc định trong application.yml hoặc cơ chế cấu hình tương ứng; thêm validation nếu hai số phải dương.

Sự khác nhau:

- Với @Value SpEL, công thức nằm trong chuỗi annotation và được đánh giá khi inject.
- Với record và phương thức Java, dữ liệu được bind có kiểu rõ ràng, công thức có thể được unit test như mã thông thường.
- Khi phép tính cần điều kiện, giới hạn, làm tròn, xử lý lỗi hoặc ghi log, Java thường dễ bảo trì hơn.

SpEL hữu ích cho những biểu thức nhỏ được một framework hỗ trợ. Nó không thay thế nhu cầu viết logic ứng dụng rõ ràng.

## 13. Khi ứng dụng chạy: giá trị có tự thay đổi không?

Một hiểu lầm khác là SpEL hoặc placeholder khiến giá trị **tự động cập nhật liên tục**. Với các trường @Value được inject khi bean khởi tạo, giá trị thường được phân giải ở thời điểm tạo bean.

Ví dụ:

~~~java
@Component
class RateLimitConfig {
    @Value("${app.max-per-minute:100}")
    private int maximum;
}
~~~

Nếu ứng dụng đã khởi động và một người sửa **APP_MAXPERMINUTE** trong shell khác, JVM đang chạy không tự nhận biến mới. Thậm chí khi một PropertySource được cập nhật, field @Value đã inject không mặc nhiên được inject lại.

Tương tự:

~~~java
@Value("#{10 * 2}")
private int fixedNumber;
~~~

Không có cơ chế nào ở đây tự tính lại biểu thức mỗi giây. Nếu cần cấu hình thay đổi nóng, ứng dụng phải sử dụng một cơ chế refresh/configuration riêng được thiết kế và kiểm soát, đồng thời xác định rõ vòng đời các bean.

**Phân biệt hai khái niệm:** “động” theo nghĩa *được quyết định khi khởi tạo từ môi trường* không đồng nghĩa “reactive” theo nghĩa *được cập nhật khi môi trường thay đổi*.

## 14. Lưu ý về placeholder trong các annotation khác

Spring có nhiều điểm tích hợp sử dụng placeholder hoặc SpEL. Nhưng việc một annotation hỗ trợ cú pháp nào cần được xác định theo contract của annotation và framework sử dụng nó.

Ví dụ:

~~~java
@Value("${app.name:Demo}")
private String name;
~~~

Cơ chế của @Value trong Spring hỗ trợ cả property placeholder và SpEL. Nhưng không thể vì thế suy ra một annotation bất kỳ do thư viện khác cung cấp sẽ phân giải **#{...}** hoặc **${...}** theo cùng cách.

Một annotation có thể:

- Chỉ đọc String nguyên văn.
- Nhận property placeholder nhưng không hỗ trợ SpEL.
- Nhận SpEL nhưng không hỗ trợ đầy đủ một số đối tượng hoặc bean references.
- Sử dụng ngữ cảnh biểu thức và thời điểm đánh giá khác nhau.

Vì vậy, khi gặp cú pháp trong một annotation lạ, hãy kiểm tra tài liệu và implementation của điểm tích hợp đó. Đừng dùng @Value làm bằng chứng cho mọi annotation trong hệ sinh thái Spring.

## 15. Dùng SpEL ở các ngữ cảnh khác với @Value

SpEL là công nghệ của Spring được tái sử dụng trong nhiều thành phần: một số điều kiện, bộ lọc, xử lý message hoặc truy vấn dữ liệu trong các module mở rộng có thể nhận biểu thức theo cú pháp riêng.

Ví dụ một hệ thống có thể hỗ trợ SpEL khi định nghĩa rule, nhưng có thể yêu cầu expression được nhập **không kèm #{...}**, vì đoạn code đó đã gọi trực tiếp parser với nội dung biểu thức. Trái lại, **#{...}** trong @Value là cú pháp template mà Spring sử dụng để nhận biết biểu thức bên trong String annotation.

Ví dụ nếu dùng SpEL parser trong code Java:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();
int result = parser.parseExpression("2 + 3").getValue(Integer.class);
~~~

Câu lệnh parseExpression nhận trực tiếp **2 + 3**, không phải chuỗi **#{2 + 3}**, bởi vì đây là chế độ parse biểu thức trực tiếp. Cú pháp template **#{...}** là cách lồng biểu thức vào một String ở những ngữ cảnh hỗ trợ template resolution.

Đây là lý do không thể lấy nguyên văn syntax của @Value rồi giả định tất cả API có SpEL đều cần cùng tiền tố.

## 16. So sánh lỗi thường gặp

### 16.1. Dùng ${...} để tính toán

~~~java
@Value("${10 * 2}")
private int result;
~~~

**Vấn đề:** Spring tìm một khóa cấu hình có tên tương ứng với nội dung placeholder; nó không được yêu cầu đánh giá phép nhân SpEL.

**Cách viết đúng khi cần phép toán:**

~~~java
@Value("#{10 * 2}")
private int result;
~~~

### 16.2. Dùng #{...} để đọc một property không có ngữ cảnh

~~~java
@Value("#{app.timeout}")
private String timeout;
~~~

**Vấn đề:** app.timeout trong SpEL không mặc nhiên có nghĩa “tìm property app.timeout của Environment”. Trừ khi evaluation context có biến/đối tượng tương ứng, biểu thức có thể không được giải quyết.

**Cách dùng để đọc cấu hình:**

~~~java
@Value("${app.timeout:5s}")
private String timeout;
~~~

### 16.3. Viết SpEL trong YAML rồi mong @ConfigurationProperties tính toán

~~~yaml
app:
  worker:
    threads: "#{2 * 4}"
~~~

**Vấn đề:** YAML không tự động biến String này thành số 8; binder của @ConfigurationProperties không đánh giá mọi String như SpEL.

**Cách xử lý:** ghi số cụ thể hoặc tính bằng Java trên các giá trị cấu hình đã được bind.

### 16.4. Dùng default để chữa dữ liệu sai

~~~java
@Value("${app.worker.threads:4}")
private int threads;
~~~

Nếu nguồn có **app.worker.threads=invalid**, placeholder đã tìm được giá trị invalid. Nó không tự chọn default 4 chỉ vì kiểu int không hợp lệ. **Cách xử lý:** sửa dữ liệu hoặc dùng validation và thông báo lỗi cấu hình rõ ràng.

### 16.5. Dùng dấu : theo nghĩa lẫn lộn

~~~text
${app.name:Guest}
#{condition ? 'A' : 'B'}
#{name ?: 'Guest'}
~~~

Các dấu hai chấm có ý nghĩa khác nhau: placeholder default; nhánh else của toán tử ba ngôi; toán tử Elvis của SpEL. Không đọc chúng như một ngữ pháp duy nhất.

### 16.6. Nội suy String không được quote khi trộn SpEL

Một ví dụ mong manh:

~~~java
@Value("#{'${app.name:Demo}' == 'Demo'}")
private boolean isDemo;
~~~

Với giá trị đơn giản, ví dụ minh họa có thể hoạt động. Nhưng khi app.name chứa dấu nháy đơn hoặc chuỗi có ý nghĩa đặc biệt, cấu trúc SpEL tạo ra sau khi thay placeholder có thể không còn đúng. **Không chèn dữ liệu tùy ý vào mã SpEL**; đọc property bằng cấu hình có kiểu rồi so sánh trong Java.

### 16.7. Dùng SpEL thay cho constructor injection

~~~java
@Value("#{@someService.someValue}")
private String value;
~~~

Nếu lớp đang thực sự phụ thuộc vào someService, inject trực tiếp một bean qua constructor thường làm quan hệ phụ thuộc và lifecycle rõ hơn. @Value với bean reference phù hợp cho các trường hợp rất đơn giản, còn logic rộng nên nằm ở class/method.

### 16.8. Quên escape trong ngôn ngữ chứa chuỗi

Trong Java source code, dấu **$**, **#**, **{** và **}** nằm trong literal String của annotation như ví dụ ở trên. Nhưng trong shell, template engine, build script hoặc một hệ thống CI dùng nội suy biến, chuỗi **${...}** có thể bị lớp khác xử lý trước khi đến Spring.

Khi một cấu hình đi qua nhiều lớp như CI → Docker Compose → container → Spring, hãy xem **lớp nào thực hiện nội suy trước**. Ví dụ Docker Compose có cơ chế biến riêng dùng dấu dollar; cú pháp của nó không tự có cùng ý nghĩa với placeholder Spring Boot.

Không nên áp dụng một kiểu escape duy nhất cho mọi ngữ cảnh; mỗi lớp parser có quy tắc riêng.

## 17. Chẩn đoán giá trị cuối cùng và lỗi tạo bean

Khi annotation @Value không nhận kết quả mong đợi, hãy kiểm tra theo đúng tầng.

**Tầng 1 — nguồn cấu hình:** khóa có tồn tại trong file, biến môi trường, JVM system property hoặc CLI không?

**Tầng 2 — tên và precedence:** tên placeholder có đúng canonical không? Một nguồn ưu tiên cao hơn có ghi đè không?

**Tầng 3 — placeholder resolution:** property có thiếu và không có default không? Default có dùng đúng dấu hai chấm không?

**Tầng 4 — SpEL evaluation:** nếu dùng #{...}, biểu thức có hợp lệ, biến/bean có tồn tại và kiểu giá trị có phù hợp không?

**Tầng 5 — conversion và injection:** giá trị cuối có chuyển được thành kiểu field/constructor parameter không?

Bảng nhận diện:

| Dấu hiệu | Nguyên nhân nên xét | Hướng kiểm tra |
| --- | --- | --- |
| “Could not resolve placeholder” | Khóa không tìm thấy, sai tên hoặc không có default | Kiểm tra property key và nguồn cấu hình |
| SpEL parse exception | Biểu thức sai cú pháp hoặc chuỗi nội suy làm hỏng biểu thức | Đọc biểu thức sau phân giải, tránh dữ liệu tùy ý |
| SpEL evaluation exception | Bean, thuộc tính hoặc phương thức không tồn tại/không truy cập được | Xem evaluation context và bean thực tế |
| Type conversion failed | Giá trị String/SpEL không phù hợp kiểu đích | So kiểu Java với dữ liệu |
| Lỗi BeanCreationException | Lỗi con xảy ra trong quá trình tạo bean | Đọc root cause, property và expression liên quan |
| Giá trị khác dự kiến nhưng bean khởi tạo được | Thứ tự ưu tiên PropertySource hoặc giá trị default | Đọc Environment.getProperty(...) và nguồn đang hoạt động |

### 17.1. Một đoạn kiểm tra không phụ thuộc SpEL

Có thể đọc giá trị cấu hình cuối bằng Environment:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class ConfigurationProbe {

    @Bean
    ApplicationRunner showConfig(Environment environment) {
        return args -> {
            System.out.println("app.worker.threads = "
                    + environment.getProperty("app.worker.threads"));
            System.out.println("app.display-name = "
                    + environment.getProperty("app.display-name"));
        };
    }
}
~~~

Kết quả của Environment giúp xác định property có mặt và giá trị được phân giải theo nguồn ưu tiên. Nó không cho biết toàn bộ quy trình đánh giá SpEL trong annotation @Value, nhưng là bước đầu tốt để tách lỗi cấu hình khỏi lỗi biểu thức.

### 17.2. Chỉ kiểm tra khóa không nhạy cảm

Nếu giá trị là mật khẩu, API token hoặc thông tin kết nối, không in giá trị vào stdout hoặc log. Có thể log tên khóa, có/không có nguồn và tên PropertySource đã được chọn ở môi trường phù hợp. Việc debug SpEL càng cần cẩn trọng vì biểu thức có thể truy cập bean hoặc thuộc tính hệ thống.

Spring Boot Actuator, khi đã được triển khai và bảo vệ, có thể cung cấp thông tin về môi trường. Các endpoint và mức hiển thị giá trị cần được cấu hình theo chính sách bảo mật; không mở public endpoint chỉ để xem một placeholder.

## 18. Bài thực hành phân biệt cú pháp

### Bài 1 — Tra cứu hay tính toán?

Hãy phân loại các annotation:

~~~java
@Value("${spring.application.name:Demo}")
private String a;

@Value("#{2 + 3}")
private int b;

@Value("${app.retry-count:5}")
private int c;

@Value("#{T(java.lang.Math).max(3, 9)}")
private int d;
~~~

Kết quả:

- a và c dùng **property placeholder**; giá trị có thể thay đổi theo Environment.
- b và d dùng **SpEL**; kết quả của các biểu thức hằng là 5 và 9.

### Bài 2 — Giá trị mặc định của placeholder

File không có app.greeting. Annotation:

~~~java
@Value("${app.greeting:Hello}")
private String greeting;
~~~

Kết quả kỳ vọng là **Hello**. Nếu file khai báo:

~~~properties
app.greeting=
~~~

thì cần phân biệt **chuỗi rỗng đã được khai báo** với **khóa không tồn tại**. Không nên kết luận luôn nhận Hello.

### Bài 3 — Cấu hình số và biểu thức

File:

~~~properties
app.factor=7
~~~

Annotation:

~~~java
@Value("#{${app.factor:3} * 4}")
private int score;
~~~

Kết quả kỳ vọng là **28** trong ngữ cảnh @Value hỗ trợ placeholder và SpEL, không có override khác. Bỏ app.factor thì mặc định 3 được dùng và score là **12**.

Hãy thêm biến môi trường **APP_FACTOR=9** rồi quan sát giá trị. Trong thứ tự PropertySource chuẩn, nếu không có override cao hơn, kết quả có thể thành **36**.

### Bài 4 — SpEL truy cập bean

Cho bean:

~~~java
@Component("priceRules")
class PriceRules {
    public int getDefaultDiscount() {
        return 5;
    }
}
~~~

Dùng:

~~~java
@Value("#{@priceRules.defaultDiscount}")
private int discount;
~~~

SpEL truy cập bean priceRules và property defaultDiscount. Hãy giải thích vì sao đổi thành **${priceRules.defaultDiscount}** không có cùng nghĩa: placeholder sẽ tìm một khóa trong Environment chứ không tự lấy getter của bean.

### Bài 5 — Sai cú pháp khi đọc property

Một người viết:

~~~java
@Value("#{app.worker.threads:4}")
private int threads;
~~~

Họ muốn tìm property app.worker.threads và mặc định 4. Cách viết có mục tiêu đúng là:

~~~java
@Value("${app.worker.threads:4}")
private int threads;
~~~

Dấu **#{...}** không phải cách thay thế cho property placeholder. Nếu muốn xử lý logic SpEL, cần xác định rõ ngữ cảnh và các biến/bean mà biểu thức được phép sử dụng.

### Bài 6 — Property bind vào record

Cấu hình:

~~~yaml
app:
  worker:
    threads: 8
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads) {}
~~~

Hãy dự đoán điều gì xảy ra nếu sửa YAML thành:

~~~yaml
app:
  worker:
    threads: "#{4 * 2}"
~~~

Không nên dự đoán binder sẽ tính thành 8. Đây là chuỗi có cú pháp SpEL, không phải một số nguyên hợp lệ để binding thông thường. Cách phù hợp là giữ **threads: 8** hoặc tính từ các thuộc tính số có kiểu rõ trong Java.

## 19. Quy tắc chọn giải pháp

Với nhu cầu thực tế, có thể dùng bảng quyết định:

| Nhu cầu | Cách phù hợp | Ví dụ |
| --- | --- | --- |
| Đọc URL, port, timeout từ cấu hình | Property placeholder hoặc @ConfigurationProperties | ${app.api-url} |
| Có giá trị mặc định khi khóa vắng mặt | Placeholder có dấu : | ${app.enabled:false} |
| Tính một phép toán nhỏ ở điểm @Value | SpEL | #{2 * 5} |
| Đọc một thuộc tính bean theo tên trong biểu thức | SpEL khi thực sự cần | #{ @beanName.property } |
| Cấu hình nhóm trường lồng nhau, nhiều môi trường | @ConfigurationProperties | app.worker.threads |
| Kiểm tra ràng buộc dữ liệu cấu hình | @ConfigurationProperties + validation | @Min, @NotBlank |
| Quyết định logic dài và cần unit test | Java method/service | capacity = threads * tasks |
| Cập nhật cấu hình trong lúc ứng dụng chạy | Cơ chế refresh thiết kế riêng | Không dựa vào @Value cố định |

Cú pháp placeholder dễ đọc vì nó diễn đạt trực tiếp một khóa cấu hình. SpEL có thể làm nhiều việc hơn, nhưng càng nhiều khả năng thì càng cần kiểm soát độ phức tạp và nguồn dữ liệu.

## 20. Những điều cần nhớ

- **${...}** là **property placeholder**: tra cứu một tên thuộc tính từ Spring Environment; có thể dùng default bằng dấu **:**, ví dụ **${app.name:Demo}**.
- **#{...}** là **SpEL**: đánh giá một biểu thức trong ngữ cảnh Spring, ví dụ **#{10 * 2}**, **#{T(java.lang.Math).max(2, 5)}** hoặc truy cập một bean phù hợp.
- **${app.timeout:5s}** không tính toán gì; nó chọn giá trị cấu hình. **#{10 * 2}** không tìm một khóa cấu hình; nó thực hiện phép toán.
- Trong điểm tích hợp **@Value**, có thể kết hợp hai cơ chế: phân giải placeholder rồi đánh giá SpEL, chẳng hạn **#{${app.factor:2} * 3}**. Tránh nội suy chuỗi không đáng tin cậy thành mã SpEL.
- Dấu **:** của placeholder, dấu **?:** Elvis và dấu **? ... : ...** của toán tử ba ngôi SpEL có những ý nghĩa khác nhau.
- **@ConfigurationProperties** được thiết kế để bind và validate các giá trị cấu hình có cấu trúc; **không mặc nhiên đánh giá SpEL** trong mọi chuỗi YAML hoặc properties.
- **Environment.getProperty** giúp kiểm tra kết quả tra cứu cấu hình; việc đánh giá SpEL còn phụ thuộc ngữ cảnh được Spring hỗ trợ.
- Các giá trị được inject bằng @Value thường được xác định khi bean khởi tạo; sự thay đổi biến môi trường về sau không tự làm mới field đã inject.

Khi đọc một annotation hoặc file cấu hình, hãy đặt câu hỏi đầu tiên: **“Đoạn này đang tìm một thuộc tính, hay đang yêu cầu Spring tính một biểu thức?”**. Từ đó chọn placeholder, SpEL hoặc Java thông thường cho đúng trách nhiệm, giúp cấu hình dễ kiểm tra và ứng dụng dễ bảo trì.
