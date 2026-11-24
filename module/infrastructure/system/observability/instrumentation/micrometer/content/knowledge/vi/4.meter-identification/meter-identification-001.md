# Meter.Id và danh tính theo tổ hợp tên với tập tag

Trong Micrometer, một meter không chỉ được nhận diện bằng tên. Danh tính của nó trong một `MeterRegistry` được xác định bởi **tên metric và tập tag**. Hai meter có cùng tên nhưng khác ít nhất một cặp key-value tag là hai meter khác nhau; hai lần đăng ký có cùng tên và cùng tập tag sẽ trỏ đến cùng một danh tính trong registry đó.

`Meter.Id` là đối tượng mô tả danh tính này. Hiểu đúng `Meter.Id` giúp bạn dự đoán khi nào một lần đăng ký sẽ dùng lại meter đã có, khi nào một chuỗi thời gian mới được tạo, và vì sao tag động có thể làm cardinality tăng nhanh. Đây là kiến thức nền để thiết kế instrumentation Micrometer ổn định trong ứng dụng Java và khi tích hợp Spring Boot với hệ thống giám sát.

## 1. Meter, Meter.Id và MeterRegistry

Ba khái niệm có vai trò khác nhau:

- **Meter** là đối tượng ghi nhận hoặc cung cấp số đo, ví dụ `Counter`, `Gauge`, `Timer` hay `DistributionSummary`.
- **Meter.Id** mô tả meter bằng tên và các tag, đồng thời mang theo một số metadata như loại meter, mô tả và đơn vị cơ sở.
- **MeterRegistry** quản lý các meter đã đăng ký trong phạm vi registry đó và cung cấp cách đọc hoặc xuất số liệu đến backend.

Có thể hình dung `Meter.Id` như khóa để registry tra cứu meter. Giá trị counter hiện tại, thời lượng timer hoặc giá trị gauge không nằm trong danh tính. Hai counter cùng danh tính có thể có count thay đổi theo thời gian nhưng vẫn là cùng một meter.

Ví dụ một metric đếm đơn hàng thành công từ kênh web:

```java
Counter ordersCreated = Counter.builder("shop.orders.created")
        .description("Number of successfully created orders")
        .tag("channel", "web")
        .tag("result", "success")
        .register(registry);

Meter.Id id = ordersCreated.getId();
```

Ở ví dụ này, tên là `shop.orders.created`; tập tag gồm `channel=web` và `result=success`. `Meter.Id` của counter giữ thông tin nhận diện đó. Khi cần kiểm tra một meter đang được đăng ký với tên và tag nào, hãy đọc `getId()` thay vì suy đoán từ tên biến Java đang giữ meter.

## 2. Thành phần tạo nên danh tính

### 2.1. Tên metric

Tên mô tả đại lượng được đo, không nên mô tả một giá trị cụ thể của lần gọi. Ví dụ:

- `shop.orders.created` biểu diễn số đơn hàng được tạo.
- `shop.orders.processing` biểu diễn thời lượng xử lý đơn hàng.
- `shop.orders.inflight` biểu diễn số đơn hàng hiện đang được xử lý.

Tên cần ổn định giữa các lần chạy và giữa các instance cùng một dịch vụ. Đặt tên theo nghiệp vụ và đại lượng giúp người đọc dashboard hiểu số liệu mà không phải mở mã nguồn.

Tên là một phần của danh tính. `shop.orders.created` và `shop.orders.cancelled` là hai meter khác nhau, kể cả khi tập tag giống nhau. Tương tự, `shop.orders.created` và `shop.orders.created.total` là hai tên khác nhau ở cấp Micrometer; việc backend có chuẩn hóa hoặc thêm hậu tố khi xuất dữ liệu là một bước khác.

### 2.2. Tag key và tag value

Tag là một cặp key-value dùng để phân loại số liệu. Ví dụ:

```text
name = shop.orders.created
tags = {
  channel = web,
  result  = success
}
```

Tag key cho biết chiều phân loại; tag value cho biết nhóm cụ thể. Với metric đơn hàng, các chiều như `channel`, `result`, `payment_method` có thể hữu ích nếu tập giá trị được giới hạn và phục vụ một câu hỏi vận hành rõ ràng.

Mỗi tag tham gia vào danh tính. Các trường hợp sau tạo ra danh tính khác nhau:

| Tên | Tập tag | Quan hệ |
| --- | --- | --- |
| `shop.orders.created` | `channel=web` | Danh tính A |
| `shop.orders.created` | `channel=mobile` | Khác A vì value khác |
| `shop.orders.created` | `channel=web`, `result=success` | Khác A vì có thêm tag |
| `shop.orders.cancelled` | `channel=web` | Khác A vì tên khác |

Một tag bị thiếu cũng tạo ra danh tính khác với tag có value `unknown` hoặc value rỗng. Vì vậy, hãy thống nhất chính sách chuẩn hóa: hoặc luôn có tag với một giá trị dự phòng được định nghĩa, hoặc chủ động không gắn tag đó. Tránh để cùng một metric lúc có tag, lúc không có tag chỉ vì các nhánh code xử lý đầu vào khác nhau.

### 2.3. Thứ tự tag không tạo danh tính mới

Về mặt ý nghĩa, tập tag là một tập cặp key-value; thứ tự truyền các tag không làm thay đổi danh tính. Micrometer chuẩn hóa thứ tự tag theo key khi tạo cấu trúc `Tags`, nhờ đó hai lần đăng ký sau tương đương:

```java
Counter fromWeb = Counter.builder("shop.orders.created")
        .tag("channel", "web")
        .tag("result", "success")
        .register(registry);

Counter sameIdentity = Counter.builder("shop.orders.created")
        .tag("result", "success")
        .tag("channel", "web")
        .register(registry);
```

Hai builder cung cấp cùng tên và cùng các cặp tag. Đổi thứ tự khai báo không có nghĩa là tạo một chiều dữ liệu mới. Tuy nhiên, key và value phải khớp; đổi `channel` thành `sales_channel`, hoặc đổi `web` thành `WEB`, là thay đổi dữ liệu tag và có thể tạo danh tính khác.

Để tránh lỗi khó tìm, mỗi chiều phân loại nên có một tên key thống nhất trong toàn dịch vụ. Không dùng `status` ở một nơi và `result` ở nơi khác nếu cả hai cùng diễn tả một khái niệm nghiệp vụ.

## 3. Những metadata khác trong Meter.Id

Ngoài tên và tag, `Meter.Id` còn cung cấp metadata hữu ích:

| Metadata | Ý nghĩa | Có tạo danh tính mới khi thay đổi không? |
| --- | --- | --- |
| `type` | Loại meter như counter, gauge, timer hoặc distribution summary | Không; nhưng đăng ký khác loại meter dưới cùng tên và tag là xung đột thiết kế cần tránh. |
| `description` | Mô tả ý nghĩa của metric | Không |
| `baseUnit` | Đơn vị cơ sở của số đo, ví dụ `bytes`, `seconds` hoặc `items` | Không |

Điểm quan trọng là không dùng description hay base unit để phân biệt hai đại lượng. Nếu hai đại lượng có ý nghĩa khác nhau, hãy đặt tên khác nhau. Nếu cùng một đại lượng được ghi nhận ở nhiều nơi, hãy thống nhất đơn vị và mô tả.

Ví dụ, hai timer cùng tên và tag nhưng một nơi ghi thời gian theo milliseconds còn nơi khác lại tự quy đổi theo một quy ước khác sẽ làm số liệu khó hiểu. Hãy để API timer nhận đơn vị thời gian rõ ràng và để Micrometer thực hiện quy đổi; đừng thay đổi ý nghĩa của cùng một meter giữa các call site.

Bạn có thể đọc thông tin của `Meter.Id` như sau:

```java
Meter.Id id = ordersCreated.getId();

String name = id.getName();
String channel = id.getTag("channel");
String description = id.getDescription();
String baseUnit = id.getBaseUnit();
Meter.Type type = id.getType();
Iterable<Tag> tags = id.getTags();
```

`description` và `baseUnit` có thể không được khai báo nên không nên giả định luôn có giá trị. Khi viết công cụ chẩn đoán hoặc log thông tin meter, hãy xử lý metadata tùy chọn một cách an toàn.

## 4. Quy tắc cùng danh tính trong một registry

Trong một `MeterRegistry`, khi đăng ký meter bằng cùng tên và cùng tập tag, Micrometer tra cứu danh tính tương ứng và dùng lại meter đã đăng ký. Vì vậy, nhiều thành phần trong ứng dụng có thể cùng ghi nhận một đại lượng nếu chúng thật sự có cùng ý nghĩa.

Ví dụ:

```java
Counter first = Counter.builder("shop.orders.created")
        .tag("channel", "web")
        .register(registry);

Counter second = Counter.builder("shop.orders.created")
        .tag("channel", "web")
        .register(registry);

first.increment();
second.increment();
```

Hai biến tham chiếu đến counter có cùng danh tính trong registry. Sau hai lần gọi `increment()`, count của meter đó tăng tổng cộng hai đơn vị. Đây là hành vi hữu ích khi nhiều component cùng ghi nhận một sự kiện chung, nhưng cũng có thể gây nhầm lẫn nếu hai component vô tình dùng chung tên và tag cho hai ý nghĩa khác nhau.

Nếu thêm tag `channel=mobile`, registry sẽ quản lý một meter khác:

```java
Counter mobileOrders = Counter.builder("shop.orders.created")
        .tag("channel", "mobile")
        .register(registry);
```

Meter web và meter mobile có thể được tổng hợp theo tên metric khi truy vấn, nhưng vẫn là hai chuỗi thời gian riêng vì tag value khác nhau.

Phạm vi dùng lại là từng registry. Hai `MeterRegistry` độc lập có thể chứa các meter có cùng `Meter.Id` nhưng chúng là các đối tượng trong hai registry khác nhau. Khi cả hai registry cùng xuất dữ liệu về một backend, backend có thể nhận các chuỗi thời gian cùng nhãn; hãy thiết kế pipeline xuất dữ liệu để tránh thu thập trùng ngoài ý muốn.

### 4.1. Không đăng ký nhiều loại meter cho cùng một danh tính

Tên và tập tag xác định danh tính; loại meter là metadata mô tả cách đo. Vì thế, không nên đăng ký một `Counter` và một `Gauge` với cùng tên và cùng tag rồi kỳ vọng chúng trở thành hai phép đo độc lập. Chúng đang tranh cùng một danh tính trong registry và có thể dẫn đến cảnh báo hoặc kết quả đăng ký không như mong muốn.

Nếu cần đếm tổng sự kiện và đo trạng thái hiện tại, hãy đặt tên riêng, ví dụ `shop.orders.created` cho counter và `shop.orders.inflight` cho gauge. Hai metric có ý nghĩa khác nhau cần hai tên khác nhau ngay cả khi tag giống nhau.

## 5. Quan sát Meter.Id trong mã Java

`Meter` cung cấp `getId()` để đọc danh tính. Ví dụ sau in các thành phần chính của một counter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MeterIdentityInspector {
    private final Counter ordersCreated;

    public MeterIdentityInspector(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("shop.orders.created")
                .description("Number of successfully created orders")
                .baseUnit("orders")
                .tag("channel", "web")
                .tag("result", "success")
                .register(registry);
    }

    public void printIdentity() {
        Meter.Id id = ordersCreated.getId();

        System.out.println("name=" + id.getName());
        System.out.println("tags=" + id.getTags());
        System.out.println("channel=" + id.getTag("channel"));
        System.out.println("type=" + id.getType());
        System.out.println("description=" + id.getDescription());
        System.out.println("baseUnit=" + id.getBaseUnit());
    }
}
```

Đây là cách kiểm tra tại chỗ khi một metric xuất hiện với tag không như mong đợi. Trong ứng dụng thực tế, nên dùng logger của ứng dụng thay cho `System.out.println`; ví dụ chỉ tập trung vào API đọc `Meter.Id`.

### 5.1. Tìm meter bằng tên và tag

`MeterRegistry` cũng cung cấp API tìm meter. Dùng `find()` để truy vấn theo tên và lọc theo tag:

```java
Counter webSuccess = registry.find("shop.orders.created")
        .tags("channel", "web", "result", "success")
        .counter();

if (webSuccess != null) {
    double count = webSuccess.count();
}
```

Giá trị trả về có thể là `null` nếu registry không có meter phù hợp hoặc meter không phải counter. Khi cần tìm nhiều loại meter, có thể dùng các phương thức tương ứng như `timer()`, `gauge()` hoặc `meter()`. Đừng giả định rằng chỉ truyền tên là đủ nếu cùng metric có nhiều tập tag.

## 6. Ví dụ kiểm thử danh tính bằng SimpleMeterRegistry

`SimpleMeterRegistry` phù hợp để kiểm tra quy tắc đăng ký mà không cần kết nối đến hệ thống giám sát. Test sau xác minh rằng thứ tự tag không làm đổi danh tính, còn thay đổi value tạo meter riêng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterIdentityTest {
    @Test
    void identityUsesNameAndTagSet() {
        try (var registry = new SimpleMeterRegistry()) {
            Counter first = Counter.builder("shop.orders.created")
                    .tag("channel", "web")
                    .tag("result", "success")
                    .register(registry);

            Counter sameIdentity = Counter.builder("shop.orders.created")
                    .tag("result", "success")
                    .tag("channel", "web")
                    .register(registry);

            Counter anotherIdentity = Counter.builder("shop.orders.created")
                    .tag("channel", "mobile")
                    .tag("result", "success")
                    .register(registry);

            assertThat(first).isSameAs(sameIdentity);
            assertThat(first.getId().getTag("channel")).isEqualTo("web");
            assertThat(registry.getMeters()).hasSize(2);

            first.increment();
            sameIdentity.increment();
            assertThat(first.count()).isEqualTo(2.0);
            assertThat(anotherIdentity.count()).isZero();
        }
    }
}
```

Test có ba điểm cần chú ý:

1. Hai builder đầu tiên có cùng tên và cùng cặp tag dù thứ tự khai báo khác nhau, nên chúng dùng chung meter.
2. Builder thứ ba đổi `channel` từ `web` sang `mobile`, nên registry tạo danh tính khác.
3. Hai lần tăng qua hai biến cùng danh tính làm count chung tăng lên hai; meter mobile vẫn có count bằng không.

Khi kiểm thử instrumentation của một service, hãy khởi tạo service bằng `SimpleMeterRegistry`, thực hiện hành vi cần đo rồi kiểm tra `Meter.Id` và giá trị meter. Cách này giúp phát hiện sớm trường hợp thiếu tag, sai tag key, dùng nhầm tên hoặc đăng ký trùng ngoài dự kiến.

## 7. Từ Meter.Id đến chuỗi thời gian và cardinality

Hệ thống giám sát thường biểu diễn một chuỗi thời gian bằng tên metric cộng với các nhãn (labels). Cách này tương ứng với mô hình tên và tag của Micrometer. Mỗi tổ hợp tag khác nhau tạo ra một chuỗi thời gian riêng cho cùng một tên metric.

Ví dụ metric `shop.orders.created` có hai tag:

```text
channel = web | mobile | partner
result  = success | rejected | error
```

Tổ hợp tối đa là 3 × 3 = 9 danh tính cho tên metric này. Nếu thêm tag `customer_id` có hàng trăm nghìn giá trị, số tổ hợp có thể tăng lên hàng trăm nghìn hoặc nhiều hơn. Đây là cardinality cao và có thể làm tăng đáng kể bộ nhớ, dung lượng lưu trữ, chi phí scrape và thời gian truy vấn.

Vì tag là thành phần của `Meter.Id`, quyết định gắn tag cũng chính là quyết định tạo thêm chiều dữ liệu. Hãy dùng tag có tập giá trị nhỏ, ổn định và hữu ích cho phân tích, chẳng hạn `channel`, `result`, `method` hoặc nhóm status code.

Không đưa các giá trị thay đổi theo từng request hoặc từng thực thể vào tag:

- ID đơn hàng, ID người dùng, email hoặc session ID;
- request ID, trace ID hoặc transaction ID;
- URL đầy đủ có path variable hoặc query string;
- exception message, nội dung tìm kiếm hoặc chuỗi đầu vào tự do.

Ví dụ, hãy dùng route template `/orders/{id}` hoặc một tag `route=order_detail` thay vì mỗi URL `/orders/1001`, `/orders/1002` tạo một value khác nhau. Nếu cần tìm một request cụ thể, log và distributed trace phù hợp hơn metrics.

### 7.1. Chuẩn hóa tag trước khi đăng ký

Một cách kiểm soát danh tính là chuẩn hóa dữ liệu đầu vào thành tập value đã định nghĩa:

```java
private String normalizeChannel(String channel) {
    return switch (channel) {
        case "web", "mobile", "partner" -> channel;
        default -> "other";
    };
}
```

Khi đăng ký meter, chỉ dùng kết quả chuẩn hóa:

```java
registry.counter(
        "shop.orders.created",
        "channel", normalizeChannel(channel)
).increment();
```

Nhờ vậy, giá trị lạ không tạo thêm một danh tính mới cho từng chuỗi đầu vào. Hãy quy định rõ cách xử lý `null`, chuỗi rỗng, chữ hoa-thường và giá trị ngoài danh sách để các call site tạo ra cùng danh tính trong cùng trường hợp nghiệp vụ.

## 8. Phân biệt danh tính Micrometer và tên xuất ra backend

`Meter.Id` là danh tính ở lớp Micrometer. Khi xuất số liệu, registry có thể áp dụng `NamingConvention` để chuyển tên và tag sang quy ước của backend. Ví dụ, một tên dạng dấu chấm có thể được chuyển thành tên dùng dấu gạch dưới ở định dạng Prometheus; timer cũng có thể được biểu diễn bằng đơn vị thời gian chuẩn của backend.

Vì vậy, tên nhìn thấy trong endpoint xuất metrics có thể khác cách viết trong `Meter.Id`. Đây là chuyển đổi định dạng, không nhất thiết có nghĩa ứng dụng đã đăng ký một meter mới. Khi viết truy vấn hoặc dashboard, hãy kiểm tra tên thực tế mà registry xuất ra.

Cũng cần lưu ý khả năng va chạm sau chuẩn hóa. Hai tên khác nhau ở lớp ứng dụng có thể trở nên giống nhau nếu backend loại bỏ hoặc thay thế một số ký tự. Hãy chọn quy ước tên rõ ràng và nhất quán, đồng thời kiểm tra đầu ra của registry trước khi triển khai dashboard.

`MeterFilter` có thể được cấu hình để loại bỏ meter, đổi tên hoặc chuẩn hóa tag trước khi meter được đăng ký. Nếu áp dụng filter, hãy tính đến việc filter có thể làm thay đổi danh tính cuối cùng trong registry. Không nên để nhiều filter độc lập đổi cùng một tag theo các quy tắc mâu thuẫn.

## 9. Các lỗi thiết kế thường gặp

- **Chỉ nhìn tên metric:** cho rằng cùng tên là cùng meter. Thực tế phải xét cả tập tag.
- **Nghĩ thứ tự tag tạo chiều mới:** đổi thứ tự khai báo tag không tạo danh tính mới nếu các cặp key-value vẫn giống nhau.
- **Không thống nhất tag key:** `channel` và `sales_channel` tạo các tập tag khác nhau dù value giống nhau.
- **Để tag động:** ID hoặc URL riêng cho từng request làm phát sinh quá nhiều danh tính và chuỗi thời gian.
- **Dùng metadata để phân biệt đại lượng:** description, base unit hoặc biến Java khác tên không tạo danh tính độc lập. Hãy đặt tên metric khác nếu ý nghĩa đo khác nhau.
- **Dùng chung tên và tag cho nhiều loại meter:** counter và gauge có cùng danh tính sẽ xung đột về thiết kế; hãy đặt tên riêng cho từng đại lượng.
- **Giả định hai registry dùng chung đối tượng meter:** mỗi registry quản lý tập meter riêng, dù chúng có thể xuất ra các nhãn giống nhau.
- **Nhầm tên trong code với tên backend:** naming convention có thể chuyển đổi tên khi xuất; hãy xác minh endpoint thực tế.
- **Chuẩn hóa không đồng nhất:** một nơi dùng `WEB`, nơi khác dùng `web` hoặc `unknown`; các value khác nhau tạo các danh tính khác nhau.

## 10. Checklist thiết kế Meter.Id

Trước khi đưa một metric vào ứng dụng, hãy kiểm tra:

- [ ] Tên metric mô tả một đại lượng và ý nghĩa nghiệp vụ ổn định.
- [ ] Các tag key được đặt tên nhất quán trong toàn dịch vụ.
- [ ] Mỗi tag value thuộc tập giá trị có giới hạn và đã có quy tắc chuẩn hóa.
- [ ] Không có ID người dùng, ID giao dịch, request ID hoặc dữ liệu tự do trong tag.
- [ ] Các thành phần cùng ghi nhận một đại lượng dùng cùng tên và tập tag.
- [ ] Các đại lượng khác nhau dùng tên riêng, kể cả khi có cùng tag.
- [ ] Description và base unit được khai báo rõ, thống nhất.
- [ ] Test xác minh cùng tên và tập tag được dùng lại, còn thay đổi tag tạo meter khác.
- [ ] Tên và tag sau khi xuất phù hợp với quy ước backend, không va chạm ngoài dự kiến.

Khi nắm vững `Meter.Id`, bạn có thể đọc danh sách meter trong registry, giải thích vì sao hai lần ghi nhận được gộp vào cùng một chuỗi thời gian hoặc tách thành hai chuỗi khác nhau, và dự đoán tác động của mỗi tag đến cardinality. Đây là nền tảng để thiết kế instrumentation Micrometer có ý nghĩa, nhất quán và dễ vận hành.
