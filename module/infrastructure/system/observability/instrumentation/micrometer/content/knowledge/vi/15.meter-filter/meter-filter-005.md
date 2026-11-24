# Thêm, đổi hoặc loại tag và đổi tên meter

Micrometer dùng tên meter và tập tag để xác định một meter ID. Tên cho biết đại lượng được đo; tag bổ sung các chiều phân tích như route, method, provider hoặc outcome. Trong một ứng dụng đã có nhiều instrumentation, có thể cần thêm ngữ cảnh chung, chuẩn hóa tag từ thư viện bên thứ ba, loại bỏ tag không phù hợp hoặc chuyển metric sang một tên thống nhất.

`MeterFilter` cho phép thực hiện những thay đổi đó tại thời điểm meter được đăng ký. Filter có thể thêm, đổi key, đổi value hoặc bỏ tag; cũng có thể ánh xạ tên meter sang tên mới. Vì các thay đổi này tác động đến meter ID, chúng ảnh hưởng đến cardinality, việc hợp nhất meter và tên chuỗi dữ liệu mà dashboard hoặc alert đang truy vấn.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích `MeterFilter` biến đổi `Meter.Id` trong quá trình đăng ký.
- Thêm tag chung cho registry hoặc thêm tag có điều kiện cho một nhóm meter.
- Đổi tên key và chuẩn hóa value của tag.
- Loại bỏ tag không cần thiết hoặc có cardinality cao.
- Đổi tên meter bằng cách ánh xạ `Meter.Id`.
- Dự đoán va chạm khi nhiều meter được ánh xạ về cùng một ID.
- Cấu hình filter trước khi binder và instrumentation đăng ký meter.

## Meter ID và vai trò của MeterFilter

Một meter ID gồm tên meter và tập tag. Ví dụ:

~~~text
http.server.requests{method="GET", route="/orders/{id}", status="2xx"}
~~~

Đổi tên meter hoặc thay đổi tag có thể làm thay đổi danh tính này. `MeterFilter` can thiệp khi registry nhận yêu cầu đăng ký meter: nó có thể chấp nhận/từ chối meter, biến đổi ID hoặc điều chỉnh cấu hình thống kê phân phối.

~~~mermaid
flowchart TD
    A[Code hoặc MeterBinder đăng ký meter] --> B[MeterRegistry nhận Meter.Id]
    B --> C[Chuỗi MeterFilter]
    C --> D[Chấp nhận, từ chối hoặc biến đổi ID]
    D --> E[Registry tìm hoặc tạo meter theo ID sau biến đổi]
    E --> F[Meter được cập nhật và export]
~~~

Filter được cấu hình trên registry và áp dụng khi meter được đăng ký. Vì vậy, hãy thêm filter trước khi binder hoặc code nghiệp vụ tạo meter. Thêm filter sau khi meter đã tồn tại không tự động quét và sửa lại các meter cũ.

## Thêm tag

### Thêm tag chung cho registry

Nếu mọi meter trong một ứng dụng cần chung ngữ cảnh như application và environment, dùng `commonTags` trên registry:

~~~java
registry.config().commonTags(
    "application", "checkout",
    "environment", "prod"
);
~~~

Một meter được đăng ký sau đó:

~~~java
Counter orders = registry.counter(
    "orders.created",
    "channel", "web"
);
~~~

sẽ có cả tag riêng `channel=web` và tag chung `application=checkout`, `environment=prod`. Common tags hữu ích khi mọi meter trong registry cần cùng một ngữ cảnh. Hãy dùng giá trị ổn định, có miền hữu hạn; không thêm request ID, user ID hoặc dữ liệu thay đổi theo từng request.

### Thêm tag có điều kiện bằng MeterFilter

Khi chỉ một nhóm meter cần tag bổ sung, có thể viết filter tùy chỉnh để ánh xạ `Meter.Id`. Ví dụ, thêm `component=payment` cho meter có tiền tố `payment.`:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(new MeterFilter() {
    @Override
    public Meter.Id map(Meter.Id id) {
        if (id.getName().startsWith("payment.")) {
            return id.withTag(Tag.of("component", "payment"));
        }
        return id;
    }
});
~~~

`withTag` tạo một ID mới có thêm tag; filter không cần thay đổi code tạo meter ở từng service. Nếu ID đã có key `component`, hãy định nghĩa rõ cách xử lý trước khi thêm để tránh hai giá trị cho cùng một key hoặc kết quả không nhất quán.

Không thêm tag có giá trị duy nhất theo từng meter hoặc từng request nếu không có lý do rõ ràng. Mỗi tổ hợp tag có thể tạo một meter ID và time series riêng. Một tag chung có một giá trị cố định thường ít làm tăng số chuỗi trong một registry, nhưng nếu giá trị của nó thay đổi giữa các môi trường hoặc instance thì backend vẫn lưu các chuỗi phân biệt theo giá trị đó.

## Đổi key của tag

Đổi key khi tên tag cũ không còn theo quy ước hoặc muốn chuẩn hóa tag từ thư viện bên ngoài. `MeterFilter.renameTag` nhận tiền tố tên meter, key cũ và key mới:

~~~java
registry.config().meterFilter(
    MeterFilter.renameTag(
        "http.server.requests",
        "uri",
        "route"
    )
);
~~~

Với meter có tên bắt đầu bằng `http.server.requests`, tag `uri` sẽ được đổi thành `route`. Ví dụ ID đầu vào:

~~~text
http.server.requests{method="GET", uri="/orders/{id}"}
~~~

sẽ được chuẩn hóa thành:

~~~text
http.server.requests{method="GET", route="/orders/{id}"}
~~~

Đây là đổi tên key, không phải đổi giá trị. Giá trị `/orders/{id}` vẫn giữ nguyên. Nếu metric đã có key `route`, hãy tránh ánh xạ thêm `uri` vào cùng key vì hai tag có thể xung đột. Trước khi triển khai, kiểm tra các instrumentation đang phát ra key mới.

## Chuẩn hóa hoặc thay đổi value của tag

Đôi khi key đã đúng nhưng value có nhiều cách viết khác nhau. Ví dụ `SUCCESS`, `success` và `Success` nên được chuẩn hóa về một giá trị thống nhất. Có thể dùng `MeterFilter.replaceTagValues`:

~~~java
import java.util.Locale;

registry.config().meterFilter(
    MeterFilter.replaceTagValues(
        "outcome",
        value -> {
            String normalized = value.toLowerCase(Locale.ROOT);
            if (normalized.equals("success") || normalized.equals("ok")) {
                return "success";
            }
            if (normalized.equals("error") || normalized.equals("failed")) {
                return "error";
            }
            if (normalized.equals("rejected")) {
                return "rejected";
            }
            return "other";
        },
        "payment.requests"
    )
);
~~~

Trong ví dụ, filter chỉ áp dụng cho meter có tiền tố `payment.requests`. Các value được ánh xạ về tập hữu hạn `success`, `error`, `rejected` hoặc `other`. Nhờ vậy dashboard không phải xử lý nhiều biến thể chữ hoa/chữ thường và cardinality dễ dự đoán hơn.

Chuẩn hóa value nên giữ đúng ý nghĩa nghiệp vụ. Không gom các trạng thái khác bản chất vào cùng một nhóm chỉ để giảm số chuỗi nếu dashboard hoặc alert cần phân biệt chúng. Với dữ liệu đầu vào có thể chứa thông tin cá nhân hoặc bí mật, hãy loại bỏ hoặc thay bằng phân loại an toàn trước khi đưa vào metrics.

## Loại bỏ tag

`MeterFilter.ignoreTags` loại bỏ những key được chỉ định khỏi ID của meter:

~~~java
registry.config().meterFilter(
    MeterFilter.ignoreTags("request_id", "user_id")
);
~~~

Filter này hữu ích như một lớp phòng vệ khi registry nhận meter từ thư viện hoặc instrumentation mà bạn không kiểm soát trực tiếp. Tuy nhiên, `request_id` và `user_id` không nên được thiết kế làm tag metrics ngay từ đầu. Dùng log hoặc trace có kiểm soát để liên kết sự kiện riêng lẻ.

Khi loại một tag, các meter trước đây khác nhau chỉ bởi tag đó có thể được ánh xạ về cùng một meter ID. Ví dụ:

~~~text
orders.created{channel="web", region="north"}
orders.created{channel="web", region="south"}
~~~

Nếu loại `region`, hai ID trên đều trở thành `orders.created{channel="web"}`. Đây là một thay đổi có ý nghĩa: dữ liệu của hai vùng sẽ được gom vào cùng meter sau khi ánh xạ. Điều này có thể đúng nếu mục tiêu là tổng hợp toàn quốc, nhưng không phù hợp nếu dashboard vẫn cần so sánh theo vùng.

Đừng xem việc bỏ tag là thao tác xóa một cột dữ liệu vô hại. Nó thay đổi danh tính và có thể hợp nhất các meter. Hãy kiểm tra xem các meter sau biến đổi có cùng loại, cùng đơn vị và cùng ý nghĩa trước khi áp dụng.

## Đổi tên meter

Đổi tên meter khi cần chuẩn hóa tên cũ, sửa lỗi đặt tên hoặc chuyển sang quy ước mới. Micrometer cho phép biến đổi `Meter.Id` bằng cách ghi đè `map` trong `MeterFilter` và dùng `withName`:

~~~java
registry.config().meterFilter(new MeterFilter() {
    @Override
    public Meter.Id map(Meter.Id id) {
        if ("legacy.orders.created".equals(id.getName())) {
            return id.withName("orders.created");
        }
        return id;
    }
});
~~~

Filter trên đổi chính xác `legacy.orders.created` thành `orders.created` và giữ nguyên tag. Nếu cần đổi một nhóm tên theo tiền tố, có thể kiểm tra `id.getName().startsWith(...)` rồi xây dựng tên mới một cách xác định.

Đổi tên meter ảnh hưởng trực tiếp đến tên metric được export. Dashboard, alert, recording rule, SLO và truy vấn hiện tại có thể vẫn tham chiếu tên cũ. Trước khi triển khai, hãy tìm các consumer của tên cũ, cập nhật truy vấn cùng đợt và quyết định thời điểm chuyển đổi. Filter không tự tạo alias để backend tiếp tục nhận cả tên cũ lẫn tên mới.

## Kết hợp nhiều phép biến đổi

Một registry có thể dùng nhiều filter. Nên gom cấu hình vào một nơi và sắp xếp theo ý nghĩa: thêm ngữ cảnh chung, chuẩn hóa key/value, loại bỏ key không được phép, rồi ánh xạ tên meter theo quy ước cuối cùng. Trình tự cụ thể phải được kiểm thử vì filter sau có thể nhìn thấy ID đã được filter trước biến đổi.

Ví dụ cấu hình:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.config.MeterFilter;

import java.util.Locale;

registry.config()
    .commonTags("application", "checkout", "environment", "prod")
    .meterFilter(MeterFilter.renameTag(
        "http.server.requests", "uri", "route"
    ))
    .meterFilter(MeterFilter.replaceTagValues(
        "outcome",
        value -> value.toLowerCase(Locale.ROOT),
        "payment.requests"
    ))
    .meterFilter(MeterFilter.ignoreTags("request_id", "user_id"))
    .meterFilter(new MeterFilter() {
        @Override
        public Meter.Id map(Meter.Id id) {
            if ("legacy.orders.created".equals(id.getName())) {
                return id.withName("orders.created");
            }
            return id;
        }
    });
~~~

Đây là ví dụ minh họa các loại biến đổi; trong dự án thực tế hãy chọn những quy tắc phù hợp với metric của mình. Nếu một key bị đổi tên rồi lại bị loại bỏ, hoặc một giá trị được chuẩn hóa trước khi một filter khác so khớp, kết quả phụ thuộc thứ tự cấu hình. Hãy giữ một quy ước duy nhất để nhóm có thể dự đoán ID cuối cùng.

## Khi nào dùng commonTags và khi nào dùng MeterFilter?

| Nhu cầu | Cách phù hợp |
|---|---|
| Mọi meter cần cùng application/environment | `registry.config().commonTags(...)` |
| Chỉ meter thuộc một nhóm cần thêm tag | `MeterFilter` tùy chỉnh với `Meter.Id.map` |
| Đổi key tag cho một họ meter | `MeterFilter.renameTag(...)` |
| Chuẩn hóa value của tag | `MeterFilter.replaceTagValues(...)` |
| Bỏ key khỏi các meter | `MeterFilter.ignoreTags(...)` |
| Đổi tên metric | `MeterFilter` tùy chỉnh và `id.withName(...)` |

`commonTags` là cách ngắn gọn cho tag chung. `MeterFilter` phù hợp khi cần quy tắc có điều kiện hoặc biến đổi ID. Không nên dùng filter tùy chỉnh cho một việc mà API chuyên biệt đã diễn đạt rõ ràng; code ngắn và cụ thể sẽ dễ review hơn.

## Cấu hình filter trước khi đăng ký meter

Các filter tác động khi registry đăng ký meter. Vì thế hãy cấu hình chúng trước khi binder hoặc code ứng dụng tạo meter:

~~~java
MeterRegistry registry = new SimpleMeterRegistry();

// 1. Cấu hình tag và filter.
registry.config().commonTags("application", "checkout");
registry.config().meterFilter(MeterFilter.renameTag(
    "http.server.request.events", "uri", "route"
));
registry.config().meterFilter(MeterFilter.ignoreTags("request_id"));

// 2. Đăng ký meter sau khi registry đã được cấu hình.
Counter requests = registry.counter(
    "http.server.request.events",
    "uri", "/orders/{id}",
    "request_id", "req-123"
);
requests.increment();
~~~

Mặc dù code ví dụ đăng ký tag `request_id`, filter loại bỏ tag đó trước khi registry tạo meter. ID cuối cùng vẫn giữ `route` sau khi đổi key và có tag chung `application`. Trong code ứng dụng mới, tốt hơn hết là không tạo tag định danh ngay từ đầu.

Với Spring Boot Actuator, registry thường do auto-configuration quản lý. Dùng `MeterRegistryCustomizer` để thêm common tags và filter trong giai đoạn cấu hình registry, trước khi meter binder và instrumentation nghiệp vụ được sử dụng:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
MeterRegistryCustomizer<MeterRegistry> metricsConfiguration() {
    return registry -> registry.config()
        .commonTags("application", "checkout")
        .meterFilter(MeterFilter.renameTag(
            "http.server.requests", "uri", "route"
        ))
        .meterFilter(MeterFilter.ignoreTags("request_id"));
}
~~~

Không tạo một registry riêng nếu mục tiêu là thay đổi registry mà Spring Boot đang dùng. Cấu hình customizer phải được đăng ký trong application context và cần kiểm tra thứ tự nếu dự án có nhiều customizer.

## Va chạm Meter ID khi biến đổi tag hoặc tên

Biến đổi ID có thể khiến hai meter khác nhau trở thành cùng một tên và tập tag. Một số trường hợp thường gặp:

- Bỏ `region` khiến meter theo từng vùng được hợp nhất.
- Đổi `uri` thành `route` trong khi ID đã có tag `route`.
- Chuẩn hóa `outcome=SUCCESS` và `outcome=success` về cùng một giá trị.
- Đổi hai tên metric cũ khác nhau về cùng tên mới.

Trước khi triển khai, hãy lập danh sách các ID đầu vào và ID sau biến đổi. Nếu hai meter được hợp nhất, xác minh chúng cùng loại meter và cùng đơn vị. Nếu chúng có ý nghĩa khác nhau, hãy giữ một chiều phân biệt hữu ích hoặc đổi tên theo quy tắc không va chạm.

Không nên đổi tên hoặc loại tag tùy tiện trong khi hệ thống đang chạy rồi kỳ vọng dữ liệu lịch sử tự chuyển theo. Backend sẽ có chuỗi mới; chuỗi cũ có thể còn tồn tại cho đến khi hết retention. Dashboard có thể hiển thị khoảng trống hoặc hai nhóm dữ liệu trong giai đoạn chuyển đổi.

## Kiểm thử MeterFilter

Dùng `SimpleMeterRegistry` để kiểm tra ID sau biến đổi mà không cần backend. Ví dụ dưới đây xác minh đổi key, bỏ tag và đổi tên meter:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
    .meterFilter(MeterFilter.renameTag(
        "http.server.request.events", "uri", "route"
    ))
    .meterFilter(MeterFilter.ignoreTags("request_id"))
    .meterFilter(new MeterFilter() {
        @Override
        public Meter.Id map(Meter.Id id) {
            if ("legacy.orders.created".equals(id.getName())) {
                return id.withName("orders.created");
            }
            return id;
        }
    });

Counter requestCounter = registry.counter(
    "http.server.request.events",
    "uri", "/orders/{id}",
    "request_id", "req-123"
);
requestCounter.increment();

assertEquals(
    1.0,
    registry.get("http.server.request.events")
        .tag("route", "/orders/{id}")
        .counter()
        .count()
);

Counter legacyCounter = registry.counter("legacy.orders.created");
legacyCounter.increment(2);

assertEquals(
    2.0,
    registry.get("orders.created").counter().count()
);

registry.close();
~~~

Các assertion trên xác minh metric được tìm bằng key mới và tên mới. Có thể bổ sung kiểm tra `Meter.Id.getTags()` để bảo đảm `request_id` không còn trong ID. Với filter chuẩn hóa value, kiểm tra nhiều biến thể đầu vào để xác nhận chúng được ánh xạ về đúng tập giá trị.

Kiểm thử `SimpleMeterRegistry` chỉ xác nhận hành vi trong registry tại ứng dụng. Khi đổi tên metric hoặc tag đang được dashboard sử dụng, cần kiểm tra thêm endpoint export và truy vấn của backend trong môi trường tích hợp.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm filter sau khi meter đã đăng ký | Meter hiện có không được sửa ngược | Cấu hình trước binder và instrumentation; tạo lại registry khi cần |
| Dùng commonTags cho tag chỉ áp dụng một metric | Tag không cần thiết xuất hiện trên nhiều meter | Dùng filter có điều kiện hoặc khai báo tag ở builder |
| Đổi key nhưng ID đã có key đích | Tag trùng hoặc xung đột | Kiểm tra tập tag đầu vào trước khi rename |
| Loại tag làm nhiều ID hợp nhất | Mất chiều phân tích hoặc meter va chạm | Xác nhận việc tổng hợp là có chủ đích |
| Chuẩn hóa value quá rộng | Các trạng thái khác nhau bị gom thành một | Giữ các nhóm có ý nghĩa vận hành |
| Đổi tên meter nhưng không cập nhật dashboard | Truy vấn và alert tiếp tục dùng tên cũ | Lập kế hoạch chuyển đổi consumer cùng thời điểm |
| Dùng tag ID cá thể | Cardinality và chi phí backend tăng cao | Loại bỏ tag định danh; dùng log/trace để điều tra |

## Ghi nhớ

- `MeterFilter` biến đổi hoặc kiểm soát meter trong lúc đăng ký.
- Dùng `commonTags` cho ngữ cảnh chung; dùng filter tùy chỉnh để thêm tag có điều kiện.
- `renameTag` đổi key; `replaceTagValues` chuẩn hóa value; `ignoreTags` loại bỏ key.
- Đổi tên meter bằng cách ánh xạ `Meter.Id` và gọi `withName(...)`.
- Cấu hình filter trước khi binder và code nghiệp vụ đăng ký meter.
- Thay đổi tag có thể hợp nhất meter ID; đổi tên có thể ảnh hưởng dashboard, alert và recording rule.
- Kiểm tra ID sau biến đổi và giữ tag có miền giá trị hữu hạn, ổn định.
- Dùng log và trace cho request ID hoặc user ID thay vì đưa chúng vào metrics.

Khi quản lý tag và tên meter tại một điểm cấu hình rõ ràng, nhóm có thể chuẩn hóa instrumentation từ nhiều thành phần mà không phải sửa từng nơi tạo meter. Điều quan trọng là hiểu ID cuối cùng sau filter, kiểm soát cardinality và cập nhật các truy vấn tiêu thụ metrics theo cùng quy ước.

## Tài liệu tham khảo

- [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — các filter có sẵn, cách biến đổi Meter.Id và thứ tự cấu hình.
- [Micrometer Core: MeterFilter API](https://javadoc.io/doc/io.micrometer/micrometer-core/1.16.6/io/micrometer/core/instrument/config/MeterFilter.html) — API renameTag, ignoreTags, replaceTagValues và custom map.
