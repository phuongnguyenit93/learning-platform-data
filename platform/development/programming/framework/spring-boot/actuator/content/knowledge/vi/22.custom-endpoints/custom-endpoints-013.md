# Kiểm soát cache, chi phí thực thi và tính an toàn của thao tác quản trị

## 1. Vì sao một endpoint quản trị cũng cần được thiết kế như một luồng tải thật?

Một endpoint Actuator tùy chỉnh có thể chỉ trả vài trường JSON nhưng phía sau lại quét hàng nghìn đối tượng, gọi cơ sở dữ liệu hoặc truy vấn một dịch vụ đang chậm. Khi ứng dụng gặp sự cố, nhiều người và công cụ thường gọi chẩn đoán cùng lúc. Endpoint được tạo ra để quan sát ứng dụng có thể trở thành nguồn tải làm sự cố nặng hơn.

Thao tác quản trị còn có thể thay đổi cấu hình, dừng một tác vụ hoặc yêu cầu xử lý lại dữ liệu. Người gọi có quyền không đồng nghĩa mọi tham số đều hợp lệ; một yêu cầu hợp lệ cũng có thể đến hai lần hoặc cạnh tranh với yêu cầu của người khác.

Cần tách ba câu hỏi:

1. **Độ mới:** người vận hành chấp nhận dữ liệu cũ trong bao lâu?
2. **Chi phí:** mỗi lần tạo kết quả dùng bao nhiêu thời gian, bộ nhớ, kết nối và công việc ở hệ thống phụ thuộc?
3. **An toàn:** ai được gọi, được thay đổi điều gì, và điều gì xảy ra nếu yêu cầu bị gửi lại hoặc đến đồng thời?

Cache giải quyết một phần chi phí đọc bằng cách dùng lại kết quả. Nó không thay thế giới hạn tải, kiểm tra quyền hay quy tắc cập nhật trạng thái.

Bài sử dụng Spring Boot 3.3.x và Spring MVC. Ví dụ thực hành cố định Spring Boot 3.3.0, chạy với JDK 21; phần mã ứng dụng cũng dùng được với cú pháp Java 17+. Không áp dụng các tên thuộc tính quản lý quyền endpoint của những phiên bản Spring Boot khác vào ví dụ này.

## 2. Hiểu đúng cache kết quả operation của Actuator

### 2.1. Cache nằm ở đâu?

Với một thao tác đọc phù hợp và TTL dương, lớp gọi operation của Actuator có thể giữ kết quả để lần gọi sau dùng lại thay vì thực thi thân phương thức.

Có thể hình dung đường đi:

```text
Yêu cầu HTTP
  → xác thực / phân quyền nếu ứng dụng có cấu hình
  → tìm operation Actuator
  → kiểm tra cache kết quả operation
      → còn dùng được: lấy kết quả đã có
      → chưa có / hết hạn: thực thi operation để tạo kết quả
  → chuyển kết quả thành phản hồi HTTP
```

Đây là sơ đồ khái niệm cho trường hợp đọc trong bài, không phải cam kết rằng mọi bộ lọc, lớp mở rộng và bộ chuyển đổi đều có thứ tự giống nhau trong mọi ứng dụng.

| Cơ chế | Nội dung được dùng lại hoặc điều khiển | Có tự thay thế cache operation không? |
| --- | --- | --- |
| Cache operation Actuator | Kết quả của thao tác đọc đủ điều kiện | Là cơ chế đang xét |
| Spring Cache, chẳng hạn `@Cacheable` | Kết quả phương thức theo thiết kế cache của ứng dụng | Không; có thể tạo thêm một tầng cache |
| Cache HTTP ở trình khách hoặc proxy | Phản hồi theo header và chính sách HTTP | Không; là một tầng khác |
| Giới hạn tốc độ yêu cầu | Tần suất được phép gửi hoặc xử lý yêu cầu | Không tạo bản chụp dữ liệu |
| Giới hạn đồng thời | Số tác vụ đang được thực thi | Không quyết định độ mới của kết quả |

Đặt TTL trong Actuator không đồng nghĩa đã đặt `Cache-Control: max-age` cho trình duyệt. Gửi header `Cache-Control: no-cache` từ trình khách cũng không phải giao thức chung để xóa cache operation phía máy chủ.

Tương tự, xóa một cache nghiệp vụ qua endpoint `caches` không nên được coi là cách xóa cache kết quả của mọi operation tùy chỉnh. Trước khi thiết kế chức năng “làm mới”, phải xác định rõ tầng cache nào cần được làm mới.

### 2.2. Điều kiện áp dụng và cách cấu hình

Trường hợp dễ kiểm soát nhất là một `@ReadOperation` không có tham số đầu vào. Ví dụ với endpoint ID `opsdemo`:

```properties
management.endpoint.opsdemo.cache.time-to-live=5s
```

Thuộc tính dùng **ID endpoint**, không dùng tên lớp Java hoặc toàn bộ đường dẫn `/actuator/opsdemo`. Tài liệu Actuator mô tả việc cache thao tác đọc không tham số qua `cache.time-to-live`. [Cấu hình cache endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Trong triển khai 3.3.0 được xét ở bài:

- TTL phải dương thì lớp gọi operation mới được bọc bằng cơ chế cache.
- `0ms` không có nghĩa giữ kết quả mãi mãi; nó khiến cơ chế cache này không được áp dụng.
- Thao tác ghi và xóa không được biến thành thao tác có cache kết quả chỉ bằng cách đặt TTL.
- Tham số bắt buộc thông thường, chẳng hạn selector để đọc một mục, không có cùng hành vi cache như thao tác đọc không đầu vào.
- Việc gọi trực tiếp `endpoint.summary()` trong Java không đi qua lớp gọi operation này; không dùng cách gọi đó để chứng minh TTL trên HTTP.

Không rút gọn thành quy tắc “cứ thấy bất kỳ tham số Java nào thì chắc chắn tắt cache”. Triển khai có xử lý riêng cho ngữ cảnh gọi và tham số tùy chọn. Khi kết quả phụ thuộc vào `Principal`, quyền, tenant hoặc một đầu vào ngầm khác, cần kiểm tra đúng cơ chế và phiên bản đang dùng. Đặc biệt, không tự tạo một cache dùng chung không có khóa phân biệt phạm vi dữ liệu.

Các kết luận về TTL, selector và lời gọi trực tiếp ở đây được quan sát lại trong thí nghiệm của phần 5, thay vì suy ra từ một lần gọi phương thức riêng lẻ.

### 2.3. TTL là giới hạn dùng lại, không phải lịch thu thập nền

Giả sử một lần đọc đã tạo bản chụp tại t₀ và TTL là 5 giây:

| Thời điểm minh họa | Điều có thể quan sát với các yêu cầu tuần tự |
| --- | --- |
| t₀ | Chưa có kết quả; operation được thực thi |
| t₀ + 1 giây | Có thể dùng lại bản chụp |
| t₀ + 3 giây | Có thể vẫn nhận dữ liệu từ lần tạo trước |
| Sau khi hết hạn | Yêu cầu tiếp theo tạo kết quả mới |
| Không có yêu cầu tiếp theo | TTL không tự gọi lại operation chỉ vì thời gian đã trôi qua |

TTL không bảo đảm cứ đúng 5 giây sẽ có một bản chụp mới. Nó cũng không phải giới hạn thời gian chạy của phương thức, không hủy câu truy vấn đang treo và không tự tạo cơ chế trả dữ liệu cũ khi làm mới thất bại.

Khi dữ liệu nguồn vốn đã là bản tổng hợp chậm cập nhật, độ cũ người dùng nhìn thấy còn gồm độ trễ của nguồn đó. Không thể tuyên bố “dữ liệu mới trong 5 giây” chỉ từ một cấu hình TTL 5 giây.

### 2.4. Phạm vi cache và yêu cầu đồng thời

Đừng coi cache operation là một kho dữ liệu dùng chung giữa các bản sao ứng dụng. Hai JVM có bộ nhớ và nhịp tạo kết quả riêng; sau khởi động lại, kết quả trong bộ nhớ không phải dữ liệu bền vững.

Cũng không dùng TTL làm bảo đảm “trong mỗi chu kỳ chỉ có đúng một lần tính”. Khi nhiều yêu cầu đồng thời gặp một kết quả chưa có hoặc hết hạn, cần kiểm tra có cơ chế gộp lần tính hay không. Triển khai đồng bộ 3.3.0 đang xét không cung cấp một cam kết chạy đúng một lần cho cả nhóm yêu cầu đó.

Nếu việc tạo kết quả rất tốn kém, hãy thiết kế giới hạn số lần làm mới đồng thời hoặc đọc một bản chụp đã được thu thập ở nơi khác. Việc đó là thiết kế của ứng dụng, không phải điều có thể suy ra chỉ từ TTL.

Kết quả được giữ để dùng lại nên là bản chụp ổn định. Nếu trả một `Map` có thể thay đổi rồi tiếp tục sửa chính instance đó, người gọi có thể thấy nội dung đổi dù thân operation chưa được chạy lại. Một record chỉ gồm số, boolean và chuỗi như trong ví dụ giúp tránh vấn đề này.

## 3. Định lượng và giới hạn chi phí thực thi

### 3.1. Đếm công việc tạo dữ liệu, không chỉ đếm số byte JSON

Có ít nhất ba loại chi phí:

- **Thu thập:** đọc cơ sở dữ liệu, gọi mạng, duyệt bộ nhớ, lấy khóa.
- **Tạo và gửi kết quả:** xây dựng đối tượng, chuyển sang JSON, giữ bộ đệm và truyền dữ liệu.
- **Tác động gián tiếp:** tranh kết nối, tranh khóa, tăng thu gom rác hoặc tạo tải cho hệ thống phụ thuộc.

Một phản hồi chỉ 2 KB vẫn có thể đắt nếu phải quét toàn bộ bảng. Ngược lại, giữ một bản chụp rất lớn trong cache có thể giảm số lần quét nhưng tăng bộ nhớ và chi phí gửi mỗi yêu cầu.

Ví dụ tính toán minh họa: có tổng cộng 20 yêu cầu mỗi giây và mỗi lần thu thập chiếm một luồng trong 100 ms. Nếu mọi lần gọi đều thực thi, tổng thời gian chiếm luồng xấp xỉ 2 giây-luồng mỗi giây, tương đương trung bình khoảng 2 lần đang chạy trong điều kiện ổn định. Đây không phải số luồng tối đa và không tính tải tăng đột biến.

Trong điều kiện lý tưởng với một bản sao, một ngữ cảnh cache, yêu cầu tuần tự và TTL 5 giây, số lần thu thập có thể giảm xuống khoảng một lần mỗi 5 giây khi được gọi đều. Tuy nhiên, số yêu cầu HTTP, kiểm tra bảo mật và lần chuyển đổi/gửi phản hồi vẫn có thể ở mức 20 mỗi giây.

### 3.2. Xác lập ngân sách riêng cho từng nguồn tải

| Nguồn chi phí | Quyết định cần có |
| --- | --- |
| Truy vấn cơ sở dữ liệu | Số dòng tối đa, chỉ mục, thời hạn truy vấn, số kết nối được phép dùng |
| Gọi dịch vụ ngoài | Thời hạn kết nối/đọc, số lần thử lại, ngân sách thời gian tổng |
| Duyệt dữ liệu | Giới hạn phần tử, độ sâu, số tác vụ con |
| Phản hồi JSON hoặc tệp | Kích thước tối đa, số mục, cách báo kết quả bị giới hạn |
| Thao tác nặng | Số lượt chạy đồng thời, hàng đợi hữu hạn, cách từ chối khi bận |
| Công việc dài | Mô hình tác vụ có ID và trạng thái thay vì giữ một HTTP request quá lâu |

Không thêm một vòng thử lại không giới hạn cho endpoint chẩn đoán đang gọi chính một dịch vụ bị sự cố. Thử lại phải nằm trong ngân sách thời gian và số lần đã xác định.

Một giới hạn thời gian chờ ở lớp HTTP cũng không tự chứng minh tác vụ bên dưới đã dừng. Trình điều khiển cơ sở dữ liệu, thư viện gọi mạng và công việc CPU cần cơ chế thời hạn hoặc hủy phù hợp. Nếu người gọi đã bỏ cuộc nhưng tác vụ vẫn chạy, việc gọi lại có thể tiếp tục làm tăng tải.

### 3.3. Khi nào nên thu thập trước?

Nếu phép đo đắt nhưng người vận hành chỉ cần số liệu gần đây, có thể để một thành phần thu thập cập nhật bản chụp có kích thước hữu hạn. Endpoint đọc bản chụp và trả thêm thời điểm thu thập, thời lượng thu thập, trạng thái lần thu thập gần nhất nếu cần.

Cần quyết định rõ khi thu thập thất bại:

- Không có dữ liệu nào: báo chưa có bản chụp.
- Có bản chụp cũ: có cho phép dùng lại không, và cũ tối đa bao lâu?
- Nguồn gặp lỗi: trả dấu hiệu lỗi hoặc dữ liệu cũ đã được đánh dấu, tránh giả vờ đây là dữ liệu vừa đo thành công.

Đây là một cơ chế thu thập nền do ứng dụng thiết kế. Nó khác việc chỉ bật TTL cho operation.

## 4. Tính an toàn của thao tác quản trị

### 4.1. Tách quan sát khỏi thay đổi

`@ReadOperation` được công bố thành GET; `@WriteOperation` thành POST; `@DeleteOperation` thành DELETE trên web. Dùng thao tác đọc để quan sát, tránh đặt hành động thay đổi cấu hình hoặc xóa dữ liệu trong GET. Hệ thống có thể gọi lại GET để giám sát, làm mới trang hoặc thử lại kết nối.

Các bộ đếm đo lường số lần đọc hoặc ghi log là tác động phục vụ quan sát. Chúng khác việc một lần GET tự thay đổi trạng thái quản trị của ứng dụng. Trong ví dụ, bộ đếm `readNumber` chỉ để quan sát thân phương thức đã chạy bao nhiêu lần; trường `enabled` chỉ đổi qua thao tác ghi.

### 4.2. Kiểm tra trước khi tạo tác động

Một yêu cầu thay đổi cần đi qua các lớp kiểm tra thích hợp:

```text
Xác thực người gọi
  → kiểm tra quyền trên hành động và đối tượng
  → kiểm tra đầu vào / phạm vi
  → kiểm tra trạng thái hoặc phiên bản hiện tại
  → áp dụng thay đổi một cách nguyên tử trong phạm vi cần bảo vệ
  → ghi nhận kết quả và thông tin kiểm toán
```

Đầu vào quản trị nên diễn tả ý định rõ ràng, ví dụ `enabled=true` thay vì lệnh `toggle`. Hai lần đặt về cùng trạng thái thường dễ kiểm soát hơn hai lần đảo trạng thái.

Không chỉ kiểm tra cú pháp. Một số nguyên hợp lệ vẫn có thể vượt giới hạn vận hành; một đường dẫn hợp lệ vẫn có thể trỏ ra ngoài phạm vi cho phép. Với dữ liệu nguồn nhạy cảm, cần trả thông tin vừa đủ để người có quyền xử lý, không trả toàn bộ cấu hình hoặc nội dung lỗi nội bộ.

### 4.3. Tránh ghi đè thay đổi của người khác

Giả sử hai người cùng đọc phiên bản 7:

- Người thứ nhất gửi thay đổi dựa trên phiên bản 7, thành công và tạo phiên bản 8.
- Người thứ hai cũng gửi thay đổi dựa trên phiên bản 7.
- Nếu cứ áp dụng yêu cầu thứ hai, nó có thể đè lên quyết định vừa được thực hiện.

Một cách xử lý là yêu cầu `expectedVersion` và kiểm tra nó **cùng thao tác cập nhật**, không kiểm tra rồi cập nhật bằng hai bước không được bảo vệ.

Trong một JVM, ví dụ dùng `AtomicReference.compareAndSet` để thay một đối tượng trạng thái bất biến chỉ khi tham chiếu hiện tại vẫn là đối tượng đã đọc. Đây là phép cập nhật nguyên tử trên tham chiếu; nó không tự tạo giao dịch cho cơ sở dữ liệu, tệp hoặc lời gọi mạng. [AtomicReference của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

Khi dữ liệu được chia sẻ giữa nhiều JVM, cần kiểm tra phiên bản ở nơi lưu trữ chung, chẳng hạn câu cập nhật có điều kiện và kiểm tra số dòng ảnh hưởng. Khóa trong bộ nhớ một tiến trình không bảo vệ các tiến trình khác.

### 4.4. Gửi lại yêu cầu không đồng nghĩa chưa thực hiện

Nếu người gọi hết thời gian chờ, thay đổi có thể đã được áp dụng. Vì vậy:

- Không tự động thực hiện lại một hành động có tác động không thể lặp an toàn.
- Cân nhắc ID yêu cầu và nơi lưu kết quả nếu cần nhận diện yêu cầu trùng.
- Phân biệt xung đột phiên bản với lỗi chưa thực thi.
- Với tác vụ dài, có thể trả ID tác vụ để kiểm tra kết quả thay vì khởi chạy một tác vụ mới sau mỗi lần mất phản hồi.

`expectedVersion` giúp tránh cập nhật từ một trạng thái cũ; nó chưa phải kho lưu kết quả theo ID yêu cầu. Một lần gửi lại có thể nhận xung đột dù lần gửi trước đã thành công. Người gọi cần đọc kết quả hiện tại hoặc tra cứu yêu cầu trước, không nên tự đổi phiên bản rồi lặp lại lệnh một cách mù quáng.

## 5. Ví dụ đầy đủ: cache một bản chụp và cập nhật có kiểm tra phiên bản

### 5.1. Phạm vi thí nghiệm

Ứng dụng mô phỏng một cờ `enabled` trong bộ nhớ. Cờ không điều khiển hệ thống bên ngoài. Có ba operation:

| Yêu cầu | Ý nghĩa |
| --- | --- |
| `GET /actuator/opsdemo` | Đọc bản tổng hợp không đầu vào, có thể được cache |
| `GET /actuator/opsdemo/live` | Đọc trạng thái qua selector bắt buộc |
| `POST /actuator/opsdemo` | Đặt trạng thái mong muốn, kèm phiên bản dự kiến |

Thí nghiệm chạy trên loopback để tập trung quan sát TTL và cập nhật. Nó chưa có Spring Security; phần 7 trình bày việc thêm kiểm soát truy cập. Cache và `expectedVersion` không được dùng làm cơ chế xác thực.

### 5.2. Tệp dự án

```text
ops-cache-demo/
├── pom.xml
└── src/main/
    ├── java/example/opscache/OpsCacheApplication.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>ops-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18081
management.endpoints.web.exposure.include=opsdemo
management.endpoint.opsdemo.cache.time-to-live=5s
```

`src/main/java/example/opscache/OpsCacheApplication.java`:

```java
package example.opscache;

import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class OpsCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpsCacheApplication.class, args);
    }

    @Bean
    OpsDemoEndpoint opsDemoEndpoint() {
        return new OpsDemoEndpoint();
    }

    public record State(boolean enabled, long version) {
    }

    public record View(String source, long readNumber, boolean enabled, long version) {
    }

    public record Change(String result, boolean enabled, long version) {
    }

    @WebEndpoint(id = "opsdemo")
    public static class OpsDemoEndpoint {
        private final AtomicReference<State> state =
                new AtomicReference<>(new State(false, 0));
        private final AtomicLong cachedReads = new AtomicLong();
        private final AtomicLong liveReads = new AtomicLong();

        @ReadOperation(produces = "application/json")
        public View summary() {
            return capture("cached", cachedReads.incrementAndGet());
        }

        @ReadOperation(produces = "application/json")
        public View current(@Selector String view) {
            if (!"live".equals(view)) {
                return null;
            }
            return capture("live", liveReads.incrementAndGet());
        }

        private View capture(String source, long readNumber) {
            State current = state.get();
            return new View(source, readNumber, current.enabled(), current.version());
        }

        @WriteOperation(produces = "application/json")
        public WebEndpointResponse<Change> configure(boolean enabled, long expectedVersion) {
            State current = state.get();
            if (expectedVersion < 0) {
                return response("INVALID_ARGUMENT", current, 400);
            }
            if (current.version() != expectedVersion) {
                return response("CONFLICT", current, 409);
            }
            if (current.enabled() == enabled) {
                return response("UNCHANGED", current, 200);
            }
            State next = new State(enabled, current.version() + 1);
            if (!state.compareAndSet(current, next)) {
                return response("CONFLICT", state.get(), 409);
            }
            return response("APPLIED", next, 200);
        }

        private WebEndpointResponse<Change> response(String result, State current, int status) {
            return new WebEndpointResponse<>(
                    new Change(result, current.enabled(), current.version()), status);
        }
    }
}
```

`State` chứa trạng thái quản trị thật trong thí nghiệm. `View` là bản chụp dùng để đọc; `Change` là biên nhận của thao tác ghi. `source="cached"` chỉ tên đường đọc có khả năng dùng cache, không phải dấu hiệu tự động cho biết một yêu cầu vừa cache hit.

`configure` dùng một lần so sánh và thay thế. Nếu có người khác thay đổi tham chiếu trước, thao tác thất bại với 409. Các mã 400 và 409 được đặt rõ bằng `WebEndpointResponse`; không dựa vào việc JSON có chữ `CONFLICT` để tự thay đổi mã HTTP.

`UNCHANGED` chỉ xuất hiện khi phiên bản dự kiến còn đúng và trạng thái mong muốn đã là trạng thái hiện tại. Nó không tăng phiên bản. Một yêu cầu có phiên bản cũ vẫn bị từ chối dù trạng thái mong muốn tình cờ trùng với hiện tại.

### 5.3. Biên dịch và chạy

Từ thư mục có `pom.xml`:

```shell
mvn clean package
java -jar target/ops-cache-demo-1.0.0.jar
```

Dùng Maven với JDK 21. Maven xử lý classpath và đóng gói các thư viện Spring; một lệnh `javac OpsCacheApplication.java` đơn lẻ chưa đủ phụ thuộc để biên dịch dự án.

Các lệnh tiếp theo dùng PowerShell. `curl.exe` tránh nhầm với alias `curl` của một số phiên bản PowerShell.

### 5.4. Quan sát lần đọc được dùng lại

Khởi động ứng dụng mới, không có yêu cầu khác gọi endpoint. Chạy hai lệnh đọc liên tiếp, trong khoảng TTL:

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

Mỗi phản hồi có các giá trị:

```json
{"source":"cached","readNumber":1,"enabled":false,"version":0}
```

`readNumber` không tăng ở lần thứ hai vì thân `summary` chưa được chạy lại. Thứ tự thuộc tính JSON không phải điều phía nhận nên dựa vào.

Nếu dừng ứng dụng rồi chạy với TTL bằng không:

```shell
java -jar target/ops-cache-demo-1.0.0.jar --management.endpoint.opsdemo.cache.time-to-live=0ms
```

Hai lần đọc mới sẽ có `readNumber` lần lượt là 1 và 2. Đường đọc vẫn ghi `source="cached"` vì chuỗi đó do mã ví dụ đặt, còn cơ chế cache đã bị tắt.

### 5.5. Ghi thành công nhưng bản chụp cũ vẫn còn

Khởi động lại với TTL mặc định 5 giây. Trong một lần chạy liên tục, đọc bản chụp rồi ghi ngay và đọc lại:

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
'{"enabled":true,"expectedVersion":0}' | Set-Content -Encoding ascii change.json
curl.exe -sS -i -X POST -H "Content-Type: application/json" --data-binary "@change.json" http://127.0.0.1:18081/actuator/opsdemo
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

`change.json` là tệp đầu vào do người học tạo trong thư mục thí nghiệm; dùng tệp giúp tránh khác biệt cách truyền dấu nháy JSON giữa các bản PowerShell.

Phần phản hồi ghi liên quan:

```http
HTTP/1.1 200
Content-Type: application/json

{"result":"APPLIED","enabled":true,"version":1}
```

Nếu lần đọc cuối vẫn nằm trong TTL của lần đọc đầu, nó vẫn có thể trả:

```json
{"source":"cached","readNumber":1,"enabled":false,"version":0}
```

Đây là hai sự kiện đồng thời đúng:

- Trạng thái trong `AtomicReference` đã là `enabled=true`, phiên bản 1.
- Kết quả đọc đã cache vẫn chứa dữ liệu của phiên bản 0.

Thao tác ghi không tự xóa cache đọc trong mẫu này. Vì vậy, không dùng bản chụp có TTL làm xác nhận duy nhất rằng thay đổi vừa thất bại. Biên nhận ghi và trạng thái đang được lưu có vai trò khác bản chụp tổng hợp.

### 5.6. Đọc trực tiếp trạng thái và kiểm tra xung đột

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo/live
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo/live
```

Khi chưa có lần gọi đường `live` nào khác, hai kết quả lần lượt là:

```json
{"source":"live","readNumber":1,"enabled":true,"version":1}
```

```json
{"source":"live","readNumber":2,"enabled":true,"version":1}
```

Selector bắt buộc khiến hai lần đọc này thực thi thân phương thức trong mẫu đang xét. Đây là đường đọc rẻ trong bộ nhớ để quan sát thí nghiệm; không nên biến mọi phép quét đắt thành một đường `live` không giới hạn rồi coi vấn đề tải đã được giải quyết.

Bây giờ gửi một thay đổi dựa trên phiên bản 0 đã cũ:

```powershell
'{"enabled":false,"expectedVersion":0}' | Set-Content -Encoding ascii stale-change.json
curl.exe -sS -i -X POST -H "Content-Type: application/json" --data-binary "@stale-change.json" http://127.0.0.1:18081/actuator/opsdemo
```

Phần phản hồi liên quan:

```http
HTTP/1.1 409
Content-Type: application/json

{"result":"CONFLICT","enabled":true,"version":1}
```

Trạng thái không bị đổi về false. Người vận hành phải đọc và đánh giá lại tình hình, không tự động lấy phiên bản 1 rồi phát lại mọi lệnh cũ.

Nếu gửi `enabled=true` với `expectedVersion=1`, mẫu trả:

```json
{"result":"UNCHANGED","enabled":true,"version":1}
```

Phiên bản không tăng vì không có thay đổi trạng thái.

### 5.7. Sau TTL và khi có cạnh tranh

Sau khi đã có bản chụp đầu tiên, không gọi thêm đường đọc tổng hợp trong lúc chờ:

```powershell
Start-Sleep -Seconds 6
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

Nếu chỉ có các lần gọi đã mô tả, kết quả mới là:

```json
{"source":"cached","readNumber":2,"enabled":true,"version":1}
```

Nếu quá trình thao tác bằng tay đã vượt 5 giây trước đó, `readNumber` có thể lớn hơn. Đó là do có lần tính mới sau hết hạn, không phải bộ đếm tự tăng theo lịch. Có thể tăng TTL thành 30 giây và chờ lâu hơn để thực hành thuận tiện.

Với một endpoint mới khởi tạo, cho hai luồng cùng gửi `enabled=true, expectedVersion=0`. Chỉ một luồng được áp dụng phiên bản 0; kết quả cần đạt là một HTTP 200, một HTTP 409, trạng thái cuối phiên bản 1. Điều này được bảo vệ bởi phép `compareAndSet`, không phải cache.

Nếu thêm tác động ngoài bộ nhớ như gọi một dịch vụ khác, không được đặt tác động đó trước phép kiểm tra nguyên tử rồi giả định CAS sẽ hoàn tác nó. Cần thiết kế giao dịch hoặc quy trình tác vụ phù hợp với chính tác động đó.

## 6. Chọn chiến lược nhất quán sau thao tác ghi

Có nhiều cách xử lý khoảng trễ giữa trạng thái mới và bản chụp đã cache:

| Nhu cầu | Cách thiết kế có thể phù hợp | Đánh đổi |
| --- | --- | --- |
| Thông tin tổng hợp chấp nhận cũ vài giây | TTL ngắn, mô tả thời điểm/phiên bản bản chụp | Có khoảng trễ quan sát |
| Phải xác nhận ngay thay đổi vừa ghi | Biên nhận ghi chứa trạng thái và phiên bản sau cập nhật | Biên nhận chỉ mô tả thời điểm thao tác đó |
| Cần đọc trạng thái hiện tại với chi phí thấp | Đường đọc rẻ không cache | Mỗi yêu cầu vẫn cần được kiểm soát quyền và tải |
| Kết quả đắt nhưng cần làm mới có điều phối | Cache/bản chụp do ứng dụng sở hữu, có cơ chế làm mới rõ | Tăng trách nhiệm quản lý đồng thời và lỗi |
| Nhiều bản sao cùng sửa trạng thái | Kiểm tra phiên bản tại kho dữ liệu chung | Cần xét tính nhất quán và giao dịch của kho đó |

Một endpoint đọc có thể trả `version` và thời điểm thu thập để người vận hành biết dữ liệu đang nói về bản nào. Tuy nhiên, không dùng phiên bản từ cache để bỏ qua kiểm tra phiên bản thật tại nơi áp dụng thay đổi.

TTL dài không tự làm thao tác ghi an toàn hơn. TTL bằng không cũng không giải quyết ghi đè đồng thời; nó chỉ thay chính sách dùng lại kết quả đọc.

## 7. Bảo vệ quyền gọi và bề mặt quản trị

### 7.1. Bật, công bố và cấp quyền là ba việc riêng

Một endpoint cần được bật và được công bố trên giao thức thích hợp để có thể được truy cập. Việc thêm ID vào `management.endpoints.web.exposure.include` không cấp quyền quản trị và không tự thiết lập một danh sách người được gọi.

Trong Spring Boot 3.3, khi có Spring Security và không tự khai báo `SecurityFilterChain`, các quy tắc tự cấu hình bảo vệ Actuator được áp dụng. Khi tự khai báo filter chain, phải tự chịu trách nhiệm cho các quy tắc còn lại; đừng để những URL ngoài phạm vi matcher rơi khỏi sự bảo vệ dự kiến. [Bảo mật endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Giới hạn địa chỉ/cổng quản trị và mạng được phép truy cập giúp giảm bề mặt tiếp xúc nhưng không thay thế xác thực và phân quyền. Nếu dùng endpoint có cả JMX, cần kiểm tra quyền và đường truy cập JMX riêng; chỉ bảo vệ HTTP chưa chứng minh mọi giao thức đều được bảo vệ.

### 7.2. Ví dụ quy tắc cho ứng dụng thí nghiệm

Đoạn dưới minh họa một filter chain cho ứng dụng chỉ phục vụ thí nghiệm này. Nó cần `spring-boot-starter-security` và cơ chế xác thực cấp vai trò `OPS_ADMIN`; đây là phần bổ sung, không nằm trong dự án chưa có bảo mật ở phần 5.

```java
package example.opscache;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("opsdemo")).hasRole("OPS_ADMIN")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

`hasRole("OPS_ADMIN")` kiểm tra authority `ROLE_OPS_ADMIN`. Quy tắc `anyRequest().denyAll()` làm rõ chính sách của các URL còn lại trong ứng dụng thí nghiệm. Với ứng dụng có chức năng khác, phải thiết kế quy tắc cho các URL đó theo yêu cầu của chúng.

Cấu hình này giữ CSRF mặc định. Có tài khoản và đúng vai trò chưa đủ để một POST thiếu token CSRF được chấp nhận. Khi phục vụ người dùng qua trình duyệt, tích hợp token đúng theo cơ chế của ứng dụng. Không tắt CSRF toàn ứng dụng chỉ để một lệnh thử POST hết bị 403.

Bộ lọc CSRF mặc định bỏ qua GET, HEAD, TRACE và OPTIONS, bảo vệ các phương thức còn lại. Vì vậy, đặt hành động thay đổi trạng thái trong GET vừa sai ý nghĩa thao tác vừa có thể đi ngoài cơ chế bảo vệ dành cho yêu cầu thay đổi. [CsrfFilter trong Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/csrf/CsrfFilter.html).

HTTP Basic trong đoạn minh họa là một lựa chọn xác thực cho thí nghiệm, không phải lý do truyền thông tin đăng nhập qua kết nối không được bảo vệ khi triển khai qua mạng. Thông tin xác thực nên đến từ cấu hình bí mật hoặc hệ thống nhận dạng của môi trường, không ghi cố định vào mã hoặc phản hồi.

### 7.3. Kiểm toán phải phản ánh kết quả thật

Với thay đổi quan trọng, dữ liệu kiểm toán thường cần: người gọi, hành động, đối tượng, thời điểm, phiên bản dự kiến, kết quả và ID yêu cầu/tác vụ nếu có. Không ghi token, mật khẩu hoặc nguyên nội dung nhạy cảm vào log.

Phân biệt ít nhất các trường hợp: bị từ chối quyền, đầu vào không hợp lệ, xung đột, đã áp dụng, không có gì cần thay đổi và đã tiếp nhận nhưng chưa hoàn tất. Việc trả 202 cho một tác vụ, nếu ứng dụng lựa chọn mô hình đó, chưa có nghĩa tác vụ đã hoàn thành thành công.

Ví dụ ở phần 5 chưa có kho kiểm toán bền vững, nhận diện yêu cầu trùng hoặc lưu trạng thái qua lần khởi động. Những trách nhiệm đó cần được thiết kế khi chuyển từ cờ mô phỏng sang thao tác quản trị thật.

## 8. Kiểm tra trước khi đưa endpoint vào sử dụng

Các nhóm kiểm tra nên phản ánh đúng hợp đồng:

| Nhóm | Tình huống cần kiểm tra |
| --- | --- |
| Cache | Lần đầu, cache hit, TTL hết hạn, TTL 0, lời gọi có selector |
| Sau ghi | Biên nhận mới nhưng bản chụp cũ; đường xác nhận trạng thái |
| Đồng thời | Hai yêu cầu cùng phiên bản, một yêu cầu thắng, trạng thái cuối nhất quán |
| Quyền | Chưa xác thực, sai vai trò, đúng vai trò; đường truy cập HTTP/JMX nếu có |
| CSRF | Yêu cầu thay đổi thiếu token, token không hợp lệ, token hợp lệ |
| Tải và lỗi | Nguồn chậm, lỗi nguồn, hết kết nối, giới hạn đồng thời, phản hồi quá lớn |
| Gửi lại | Mất phản hồi sau khi đã áp dụng, gửi trùng ID nếu có hỗ trợ |
| Nhiều bản sao | Cache riêng từng JVM và kiểm tra phiên bản ở kho dùng chung |

Khi kiểm tra cache trên web, dùng yêu cầu đi qua ánh xạ Actuator, chẳng hạn MockMvc trong ứng dụng Spring MVC hoặc HTTP thực tế. Một kiểm thử gọi thẳng phương thức chỉ kiểm tra phương thức đó; nó không chứng minh cache, bảo mật hay mã HTTP.

Với thử nghiệm TTL, ưu tiên khoảng chờ có biên an toàn và kiểm tra bộ đếm thực thi, tránh khẳng định thời điểm tuyệt đối đến từng mili giây. Với phép đo tải, ghi nhận thời lượng lần thu thập, số lần thực thi thật, số yêu cầu đang chạy, kích thước phản hồi và tải ở hệ thống phụ thuộc. Chỉ đo thời gian HTTP khi cache hit sẽ che mất chi phí của lần tính mới.

## 9. Câu hỏi tự kiểm tra

1. **TTL 10 giây có nghĩa operation chạy nền mỗi 10 giây không?** Không. Yêu cầu cần kết quả sau hết hạn mới dẫn tới lần thực thi tiếp theo trong cơ chế đang xét.
2. **TTL có làm POST tự được gửi đúng một lần không?** Không. Đây là vấn đề lặp yêu cầu và điều phối tác động.
3. **GET sau POST vẫn trả phiên bản cũ có chứng minh POST thất bại không?** Không. Phải phân biệt bản chụp có cache, biên nhận ghi và trạng thái tại nơi lưu trữ.
4. **Tắt cache có ngăn hai người ghi đè nhau không?** Không. Cần kiểm tra/cập nhật nguyên tử hoặc giao dịch thích hợp.
5. **Dùng AtomicReference có bảo vệ thay đổi trên cả cụm không?** Không. Nó bảo vệ tham chiếu trong một JVM; dữ liệu chung cần cơ chế tại nơi lưu trữ chung.
6. **Mọi lỗi 403 có phải do sai vai trò không?** Không. CSRF và các quy tắc khác cũng có thể từ chối; cần xem nguyên nhân mà không trả lộ dữ liệu nhạy cảm.
7. **Có thể tăng TTL để thay thế giới hạn đồng thời cho phép quét nặng không?** Không. Cache miss đồng thời và chi phí gửi phản hồi vẫn cần được xét.
8. **Một kết quả quản trị được cache có thể dùng để bỏ qua xác thực các lần sau không?** Không. Việc dùng lại dữ liệu không cấp quyền cho yêu cầu mới.
