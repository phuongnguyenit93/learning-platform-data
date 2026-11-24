# Xóa meter, đóng registry và phạm vi ảnh hưởng đến dữ liệu đã xuất

Micrometer quản lý meter trong bộ nhớ của ứng dụng thông qua MeterRegistry. Trong vòng đời ứng dụng, đôi khi cần gỡ một meter đã đăng ký, dọn toàn bộ meter của một registry tạm hoặc đóng registry để giải phóng tài nguyên. Ba thao tác này ảnh hưởng đến trạng thái đo lường trong tiến trình Java và hoạt động export tiếp theo.

Điều quan trọng là phải phân biệt vòng đời meter trong ứng dụng với dữ liệu đã được hệ thống giám sát nhận. Xóa meter khỏi registry không phải là lệnh xóa lịch sử metrics ở backend. Khi một mẫu đo đã được gửi hoặc scrape thành công, dữ liệu đó thuộc hệ thống nhận và tuân theo chính sách lưu trữ, truy vấn và xóa dữ liệu của backend.

## 1. Hai phạm vi dữ liệu trong pipeline

Có thể chia dữ liệu metrics thành hai phạm vi:

1. **Trạng thái trong ứng dụng:** meter, số đo hiện tại, tags và registry đang quản lý chúng.
2. **Dữ liệu đã xuất:** các mẫu đã được scrape hoặc push đến backend và được backend lưu trữ.

~~~mermaid
flowchart LR
    subgraph APP["Trong tiến trình ứng dụng"]
        A["Instrumentation"] --> B["Meter"]
        B --> C["MeterRegistry"]
        C --> D["Endpoint scrape / exporter"]
    end
    D --> E["Backend giám sát"]
    E --> F["Chuỗi thời gian đã lưu"]
    G["remove / clear / close"] -.-> B
    G -.-> C
~~~

Các thao tác remove, clear và close tác động đến registry hoặc meter trong vùng ứng dụng. Chúng không tự động gửi yêu cầu xóa các mẫu đã lưu trong vùng backend.

Ví dụ, một counter orders.created đã tăng lên 25 và được Prometheus scrape. Nếu ứng dụng xóa counter đó khỏi registry, endpoint sẽ không còn xuất meter này trong những lần scrape tiếp theo. Các mẫu trước đó vẫn thuộc lịch sử lưu trữ của Prometheus và được giữ theo retention của hệ thống.

## 2. Xóa một meter bằng remove

MeterRegistry cung cấp thao tác remove để gỡ một meter cụ thể khỏi registry. Có thể truyền đối tượng meter hoặc Meter.Id của nó. Ví dụ:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class TemporaryMetrics {

    private final MeterRegistry registry;

    public TemporaryMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void removeTemporaryCounter() {
        Counter counter = registry.counter(
            "jobs.temporary.completed",
            "job_type", "reindex"
        );

        counter.increment();

        // Gỡ meter khỏi registry hiện tại.
        registry.remove(counter);
    }
}
~~~

Sau khi remove hoàn tất:

- Registry không còn quản lý meter vừa bị gỡ và không đưa meter đó vào những lần thu thập tiếp theo.
- Những tham chiếu Java đã giữ đến đối tượng meter cũ vẫn có thể còn tồn tại trong code. Gọi increment() trên tham chiếu cũ không làm meter đó tự đăng ký lại vào registry.
- Nếu ứng dụng gọi registry.counter(...) với cùng tên và tags sau đó, registry có thể đăng ký một meter mới. Meter mới có trạng thái đo trong tiến trình mới, ví dụ counter bắt đầu lại từ 0.
- Việc remove không thu hồi các mẫu đã được backend nhận trước đó.

Nếu cần xóa theo định danh thay vì giữ đối tượng meter, có thể dùng Meter.Id:

~~~java
Counter counter = registry.counter(
    "jobs.temporary.completed",
    "job_type", "reindex"
);

registry.remove(counter.getId());
~~~

Chỉ gỡ meter khi ứng dụng thực sự quản lý vòng đời của meter đó. Không nên remove một meter dùng chung trong khi các thành phần khác vẫn đang ghi nhận vào nó. Nếu một luồng vẫn giữ tham chiếu cũ, số đo của luồng đó có thể tiếp tục tăng trên đối tượng đã bị tách khỏi registry và không được export.

## 3. Xóa toàn bộ meter bằng clear

clear() gỡ toàn bộ meter đang được registry quản lý. Đây là thao tác có phạm vi lớn hơn remove:

~~~java
registry.clear();
~~~

Sau clear, registry không còn các meter đã đăng ký trước đó. Khi code đăng ký lại meter, registry tạo hoặc trả về meter mới theo tên và tags được yêu cầu. Các giá trị tích lũy trong meter cũ không được khôi phục từ backend.

Chỉ dùng clear khi thực sự muốn dọn toàn bộ registry, ví dụ:

- Kết thúc một lần chạy kiểm thử và dọn registry riêng của test.
- Kết thúc một phiên đo tạm có registry riêng, không dùng chung với phần còn lại của ứng dụng.
- Thay thế toàn bộ tập meter của một thành phần có vòng đời độc lập và đã bảo đảm không còn ghi nhận đang diễn ra.

Không gọi clear trên registry dùng chung của ứng dụng chỉ để xóa một metric sai. Thao tác này có thể làm biến mất cả metrics JVM, HTTP server, database pool và metrics nghiệp vụ đang được các thành phần khác sử dụng. Hãy dùng remove cho một meter cụ thể hoặc sửa cấu hình/đăng ký để ngăn meter không mong muốn.

## 4. Đóng registry bằng close

close() kết thúc vòng đời của registry và giải phóng tài nguyên mà implementation đó quản lý. Tùy registry, tài nguyên có thể gồm scheduler xuất metrics định kỳ, kết nối hoặc thành phần hỗ trợ exporter.

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

try {
    registry.counter("batch.completed").increment();
    // Thực hiện công việc sử dụng registry tạm.
} finally {
    registry.close();
}
~~~

Đóng registry phù hợp với registry được tạo riêng cho một tác vụ hoặc một phạm vi sở hữu rõ ràng. Sau khi close, không tiếp tục sử dụng registry đó như một registry đang hoạt động. Nếu cần đo lường tiếp, hãy tạo và cấu hình một registry mới với vòng đời mới.

Trong ứng dụng Spring Boot, MeterRegistry thường được tạo và quản lý bởi application context. Các service nên inject registry dùng chung và để Spring quản lý vòng đời bean khi ứng dụng dừng. Không tự gọi close() trên registry được inject từ một service nghiệp vụ; làm vậy có thể ảnh hưởng đến mọi thành phần đang dùng registry đó.

Đặc biệt, không đóng Metrics.globalRegistry hoặc registry dùng chung của ứng dụng từ một component có vòng đời ngắn. Registry dùng chung chỉ nên được đóng bởi thành phần sở hữu vòng đời toàn ứng dụng.

## 5. So sánh remove, clear và close

| Thao tác | Phạm vi | Mục đích | Tác động đến backend |
| --- | --- | --- | --- |
| remove(meter) hoặc remove(meterId) | Một meter | Gỡ meter cụ thể khỏi registry | Ngừng xuất meter đó ở những lần thu thập sau; không xóa lịch sử đã nhận |
| clear() | Tất cả meter trong registry | Dọn toàn bộ meter đã đăng ký | Ngừng xuất các meter đã bị gỡ; không xóa lịch sử đã nhận |
| close() | Vòng đời registry và tài nguyên của nó | Kết thúc sử dụng registry, giải phóng tài nguyên | Dừng hoạt động export/thu thập do registry quản lý; không xóa dữ liệu backend |

Các thao tác có thể có chi tiết triển khai khác nhau giữa các loại registry. Hãy xem tài liệu của registry cụ thể khi cần dựa vào hành vi shutdown, flush cuối cùng hoặc tài nguyên exporter. Không coi close() là một cơ chế xóa dữ liệu từ xa.

## 6. Điều gì xảy ra với dữ liệu đã export?

### Với mô hình pull như Prometheus

Prometheus chủ động scrape endpoint metrics của ứng dụng. Khi meter bị remove hoặc clear, endpoint của registry sẽ không còn cung cấp meter đó trong những lần scrape sau.

Prometheus xử lý việc một chuỗi thời gian không còn xuất hiện theo cơ chế staleness và quy tắc truy vấn của chính Prometheus. Các mẫu lịch sử đã lưu vẫn có thể truy vấn trong khoảng retention. Xóa meter khỏi ứng dụng không tương đương với xóa chuỗi thời gian khỏi TSDB.

Nếu meter được đăng ký lại với cùng tên và tags, backend có thể nhìn thấy lại cùng identity chuỗi thời gian sau một khoảng gián đoạn. Với Counter, giá trị trong tiến trình mới có thể bắt đầu từ 0; hệ thống truy vấn cần xử lý counter reset theo semantics của backend.

### Với mô hình push

Registry hoặc exporter gửi dữ liệu đến backend theo chu kỳ. Khi meter bị remove, các lần publish tiếp theo sẽ không còn chứa meter đó, tùy cơ chế của registry.

Các mẫu đã push trước đó vẫn nằm trong backend cho đến khi hết retention hoặc được xóa bằng cơ chế quản trị riêng của backend. Nếu đang có một lần publish hoặc batch gửi dữ liệu diễn ra, việc remove không nhất thiết thu hồi được payload đã được tạo hoặc gửi đi.

### Với close

Đóng registry thường dừng scheduler hoặc tài nguyên export mà registry quản lý. Sau đó, ứng dụng không còn luồng scrape/push bình thường từ registry đó. Tuy nhiên, các mẫu đã nhận ở backend vẫn tồn tại theo chính sách lưu trữ.

Không giả định mọi registry đều tự động gửi một lần flush cuối cùng khi close. Nếu hệ thống cần bảo đảm flush trước khi dừng, hãy kiểm tra hợp đồng và cấu hình của registry/exporter cụ thể.

## 7. Muốn xóa dữ liệu ở backend thì phải làm gì?

Micrometer tập trung vào instrumentation và chuyển đổi metrics từ ứng dụng. API remove, clear và close quản lý meter/registry ở phía ứng dụng. Việc xóa các chuỗi thời gian hoặc mẫu đã lưu cần thao tác theo khả năng của hệ thống nhận.

Quy trình thường gồm:

1. Xác định backend đang lưu dữ liệu, metric name, tags và khoảng thời gian cần xử lý.
2. Kiểm tra backend có hỗ trợ xóa series, xóa dữ liệu theo selector hoặc chính sách retention hay không.
3. Dùng API, giao diện quản trị hoặc quy trình vận hành được backend hỗ trợ để thực hiện xóa nếu thực sự cần.
4. Xác minh truy vấn sau thao tác và kiểm tra xem ứng dụng còn tiếp tục xuất lại metric đó hay không.

Ví dụ, nếu chỉ remove meter ở ứng dụng nhưng instrumentation vẫn đăng ký lại meter trong mỗi request, dữ liệu sẽ tiếp tục xuất hiện. Nếu muốn ngừng thu thập, cần sửa hoặc tắt đường instrumentation tương ứng. Nếu muốn xóa lịch sử đã lưu, phải dùng cơ chế xóa của backend.

Chính sách xóa dữ liệu từ xa thường có ảnh hưởng lớn hơn remove cục bộ và có thể phụ thuộc quyền quản trị, retention hoặc cơ chế tombstone của backend. Không suy luận rằng một thao tác trong Micrometer sẽ xóa dữ liệu trên mọi hệ thống nhận.

## 8. Tránh dùng remove để xử lý cardinality cao

Một cách làm không phù hợp là tạo meter cho từng request hoặc từng người dùng rồi remove meter sau khi xử lý xong. Cách này vẫn có thể tạo ra lượng meter rất lớn trong thời gian chạy, gây áp lực cho registry và backend. Việc remove liên tục còn làm vòng đời meter khó dự đoán và tạo ra khoảng trống trong dữ liệu.

Hãy giới hạn tag value ngay từ đầu:

- Dùng route template thay cho URL chứa ID thực tế.
- Dùng enum hoặc danh sách value hữu hạn cho result, operation và channel.
- Không đưa user ID, order ID, session ID, email hoặc request ID vào tags.
- Dùng MeterFilter để giới hạn hoặc từ chối các tổ hợp meter ngoài dự kiến.
- Đưa định danh chi tiết vào trace hoặc log khi cần truy vết một request cụ thể.

Ví dụ, thay vì tạo metric riêng cho mỗi mã đơn hàng:

~~~java
// Không nên: orderId tạo ra cardinality gần như không giới hạn.
registry.counter(
    "orders.processed",
    "order_id", order.getId()
).increment();

// Nên: dùng các chiều có tập giá trị hữu hạn.
registry.counter(
    "orders.processed",
    "channel", normalizeChannel(order.getChannel()),
    "result", "success"
).increment();
~~~

## 9. Quản lý vòng đời registry trong Spring Boot

Trong ứng dụng Spring Boot, registry thường là bean được auto-configuration tạo dựa trên dependency và cấu hình. Service nhận registry qua constructor injection:

~~~java
@Service
public class PaymentMetrics {

    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSuccess() {
        registry.counter(
            "payments.completed",
            "result", "success"
        ).increment();
    }
}
~~~

Service không sở hữu vòng đời của registry nên không nên đóng registry trong destroy method của chính service đó. Application context quản lý việc khởi tạo và shutdown các bean theo cấu hình của Spring Boot.

Nếu cần một registry độc lập trong một tác vụ hoặc bài kiểm thử, hãy tự tạo, dùng trong phạm vi đó và đóng ở điểm kết thúc:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
try {
    // Đăng ký meter và thực hiện assertions.
} finally {
    registry.close();
}
~~~

Tách registry riêng cho test giúp việc clear hoặc close không ảnh hưởng đến registry đang dùng bởi các thành phần khác. Trong production, ưu tiên registry dùng chung do framework quản lý, trừ khi có yêu cầu kiến trúc rõ ràng về nhiều registry với vòng đời tách biệt.

## 10. Kiểm thử hành vi remove và clear

SimpleMeterRegistry phù hợp để kiểm tra trạng thái cục bộ mà không cần backend:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter(
    "orders.temporary",
    "scope", "test"
);
counter.increment();

assertThat(registry.getMeters()).contains(counter);

registry.remove(counter);

assertThat(registry.getMeters()).doesNotContain(counter);

Counter replacement = registry.counter(
    "orders.temporary",
    "scope", "test"
);

assertThat(replacement).isNotSameAs(counter);
assertThat(replacement.count()).isEqualTo(0.0);
~~~

Có thể kiểm tra clear riêng:

~~~java
registry.counter("test.first").increment();
registry.counter("test.second").increment();

registry.clear();

assertThat(registry.getMeters()).isEmpty();
~~~

Những kiểm thử này chỉ xác minh registry trong bộ nhớ. Chúng không thể chứng minh backend đã xóa lịch sử hoặc đã đánh dấu chuỗi thời gian stale. Để xác minh luồng đầy đủ, cần integration test với registry/exporter thực tế và backend thử nghiệm.

## 11. Checklist trước khi xóa meter hoặc đóng registry

Trước khi thao tác, hãy xác định:

- Meter này có được thành phần khác sử dụng hoặc giữ tham chiếu không?
- Cần gỡ một meter hay dọn toàn bộ registry?
- Registry có phải bean dùng chung do Spring Boot quản lý không?
- Có thao tác nghiệp vụ đang chạy và ghi nhận vào meter không?
- Backend đang dùng pull hay push?
- Dữ liệu lịch sử đã xuất có cần giữ theo retention không?
- Mục tiêu là ngừng xuất metrics hay xóa lịch sử đã lưu?
- Nếu cần xóa từ xa, backend có cơ chế quản trị riêng nào?

Remove phù hợp khi cần gỡ một meter khỏi registry; clear dùng cho việc dọn toàn bộ meter của registry; close dùng khi kết thúc vòng đời registry và giải phóng tài nguyên. Cả ba đều quản lý trạng thái ở phía ứng dụng. Dữ liệu đã được backend nhận tiếp tục tuân theo chính sách của backend, vì vậy cần chọn đúng công cụ theo phạm vi dữ liệu muốn thay đổi.
