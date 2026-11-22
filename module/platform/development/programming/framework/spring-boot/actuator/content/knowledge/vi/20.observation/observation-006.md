# Tùy chỉnh tên và tag bằng ObservationConvention

## 1. Vì sao cần một quy ước tên và nhãn riêng?

Giả sử nhiều phương thức cùng quan sát quá trình xử lý đơn hàng. Nếu mỗi nơi tự đặt tên và nhãn, rất dễ xuất hiện những dạng như:

```text
checkout
orders.checkout
process-order
checkout.demo-101
```

Chúng có thể mô tả cùng một loại công việc nhưng bị chia thành nhiều nhóm dữ liệu. Trường hợp đưa mã đơn hàng vào tên còn làm số tên tăng theo từng lần thực hiện.

Vấn đề tương tự xảy ra với nhãn (tag): nơi dùng `channel=web`, nơi dùng `source=website`, nơi khác ghi trực tiếp một chuỗi người dùng nhập. Khi đó, biểu đồ và cảnh báo khó so sánh, còn số tổ hợp nhãn có thể tăng không kiểm soát.

`ObservationConvention` tách quy tắc **đặt tên và tạo metadata** khỏi phần mã **bắt đầu, chạy và kết thúc công việc**:

```text
Dữ liệu của một lần thực hiện
           |
           v
    Observation.Context
           |
           v
    ObservationConvention
    - tên quan sát
    - tên theo ngữ cảnh
    - nhãn có ít giá trị
    - nhãn có nhiều giá trị
           |
           v
       Observation
           |
           v
 Handler phù hợp → metrics / traces / hành vi quan sát khác
```

Nhờ đó, ta có thể đổi quy ước nhãn mà vẫn giữ nguyên nghiệp vụ được quan sát. Convention không thay thế vòng đời `start/scope/error/stop`, cũng không tự gửi dữ liệu ra backend.

Bài thực hành sẽ dùng bốn trường hợp trên cùng một chương trình: mặc định, toàn cục, tùy chỉnh truyền trực tiếp và factory nhận tên trực tiếp. Mục tiêu là hiểu **convention nào được chọn và metadata nào thực sự có trong context**, thay vì chỉ thấy tên lớp đã được khai báo.

## 2. Các phương thức quan trọng của ObservationConvention

Convention có kiểu ngữ cảnh cụ thể, ví dụ:

```java
ObservationConvention<CheckoutContext>
```

`CheckoutContext` là lớp của ứng dụng kế thừa `Observation.Context`; ví dụ đầy đủ sẽ được định nghĩa ở phần thực hành.

| Phương thức | Vai trò | Ví dụ trong bài |
| --- | --- | --- |
| `supportsContext(Observation.Context)` | Cho biết convention hỗ trợ loại context nào | Chỉ chấp nhận `CheckoutContext` |
| `getName()` | Cung cấp tên observation ổn định | `checkout.process` |
| `getContextualName(context)` | Cung cấp tên mô tả theo ngữ cảnh | `process checkout` |
| `getLowCardinalityKeyValues(context)` | Tạo nhãn có tập giá trị được kiểm soát | `channel=web`, `result=success` |
| `getHighCardinalityKeyValues(context)` | Tạo metadata có thể có rất nhiều giá trị khác nhau | Mã đơn hàng giả lập `order.id=demo-101` |

Không cần tạo nghiệp vụ trong các getter này. Chúng nên đọc dữ liệu đã có trong context và trả về quy ước tương ứng.

### 2.1. Tên ổn định khác với tên theo ngữ cảnh

`getName()` mô tả **loại công việc**, không phải định danh từng lần thực hiện. Ví dụ:

```text
Hợp lý:    checkout.process
Không nên: checkout.demo-101
Không nên: checkout.2026-11-05T10:23:41
```

Tên observation thường được tích hợp metrics dùng làm cơ sở đặt tên meter. Từng registry/backend còn có thể chuẩn hóa tên theo định dạng riêng. Đổi tên observation có thể làm các truy vấn, dashboard hoặc cảnh báo đang dùng tên cũ không còn khớp.

`getContextualName(context)` là tên mô tả dễ đọc hơn. Một tích hợp tracing có thể dùng nó để đặt tên span. Nó không phải nơi tự động gom mọi tham số nghiệp vụ vào tên.

Trong bài, `checkout.process` và `process checkout` cố ý cùng mô tả một loại công việc bằng hai vai trò khác nhau. Đặt tên theo ngữ cảnh cũng cần cân nhắc độ ổn định và khả năng tìm kiếm, không nối tùy tiện thông tin riêng của người dùng.

### 2.2. Nhãn và tên giải quyết hai câu hỏi khác nhau

Tên trả lời “đang quan sát công việc gì?”. Nhãn trả lời “công việc đó thuộc nhóm nào?”.

Ví dụ:

```text
name = checkout.process
low  = {channel=web, result=success}
```

Giữ một tên công việc rồi phân nhóm bằng nhãn hữu hạn giúp so sánh `web` với `store` rõ hơn việc tạo một tên metric mới cho mọi biến thể của dữ liệu đầu vào.

Không gộp số tiền, danh sách sản phẩm hoặc mã đơn vào một nhãn chuỗi lớn để thay cho việc mô hình hóa các chiều dữ liệu thực sự cần đo.

### 2.3. supportsContext là ranh giới áp dụng

Trong ví dụ:

```java
@Override
public boolean supportsContext(Observation.Context context) {
    return context instanceof CheckoutContext;
}
```

Điều kiện này quan trọng khi convention được tìm qua cấu hình registry, nhất là convention toàn cục. Registry có thể được dùng cho HTTP, database và nghiệp vụ riêng; một convention checkout không nên xử lý mọi loại context đó.

Tên quan sát giống nhau không biến một `Observation.Context` thông thường thành `CheckoutContext`. Generic ở khai báo cũng không thay thế việc chọn đúng context khi instrumentation chạy.

Khi truyền convention tường minh, instrumentation vẫn phải truyền đúng loại context mà convention đọc; không cố ép một convention nghiệp vụ vào context HTTP không tương thích.

## 3. Phân loại nhãn theo số giá trị

### 3.1. Low cardinality phải được thiết kế, không chỉ đặt tên như vậy

Cardinality là số tổ hợp giá trị tạo ra các chuỗi hoặc nhóm dữ liệu khác nhau. Một nhãn được khai báo qua `getLowCardinalityKeyValues` không tự trở thành ít giá trị nếu ta trả về dữ liệu không giới hạn.

Ví dụ thiết kế trong bài:

| Nhãn | Tập giá trị dự kiến | Cách tạo |
| --- | --- | --- |
| `channel` | `web`, `store`, `other` | Chuẩn hóa đầu vào vào ba nhóm |
| `result` | `pending`, `success`, `failure` | Trạng thái hữu hạn của ví dụ |
| `deployment.region` | Một số vùng triển khai đã biết | Lấy từ cấu hình được kiểm soát |
| `tier` | Một số cấp dịch vụ đã định nghĩa | Không dùng nguyên tên tùy ý từ yêu cầu |

Nếu `channel` nhận trực tiếp mọi chuỗi bên ngoài, tập giá trị có thể rất lớn dù tên nhãn nghe có vẻ đơn giản. Vì vậy ví dụ ánh xạ mọi giá trị không phải `web/store`, kể cả `null`, về `other`.

Sự chuẩn hóa này phục vụ **phân nhóm quan sát**. Nó không tự sửa hoặc xác thực nghiệp vụ. Nếu kênh không hợp lệ phải bị từ chối theo hợp đồng nghiệp vụ, phần xử lý nghiệp vụ vẫn phải thực hiện điều đó.

Với ba giá trị channel, ba giá trị result và hai giá trị tier, trần tổ hợp minh họa là:

```text
3 × 3 × 2 = 18 tổ hợp
```

Con số này chỉ là mô hình cho các chiều đã liệt kê. Tổng số chuỗi thực tế còn phụ thuộc instance, các nhãn khác, meter và histogram được tạo.

### 3.2. High cardinality dành cho chi tiết, không phải một lối đi để tránh mọi giới hạn

Mã đơn hàng có thể có giá trị khác nhau ở gần như mỗi lần thực hiện. Đưa nó vào nhãn metrics khiến số chuỗi có thể tăng theo số đơn.

Trong ví dụ, các mã giả lập `demo-101`, `demo-102` được đặt vào nhóm high cardinality để phân biệt với nhãn phân nhóm hữu hạn.

Trong tích hợp thông thường của Spring Boot, low cardinality được dùng cho metrics và traces, còn high cardinality dành cho traces. Custom handler có thể đọc cả hai; nó phải tự tuân theo thiết kế dữ liệu của mình. Vì vậy, việc console của bài in dòng `HIGH` không có nghĩa ta đã cấu hình một metrics backend nhận nhãn đó.

High cardinality vẫn có chi phí lưu trữ, tìm kiếm và yêu cầu quản lý dữ liệu. Chỉ đưa định danh vào khi có mục đích điều tra rõ ràng; không thêm mật khẩu, token hoặc toàn bộ nội dung yêu cầu. Đây là quyết định nội dung metadata, không phải tính năng tự bảo vệ của convention.

## 4. Convention nào được chọn?

Phải phân biệt ba vai trò:

1. **Default convention:** quy ước dự phòng do instrumentation cung cấp.
2. **Global convention:** quy ước đăng ký ở registry, có điều kiện hỗ trợ context.
3. **Custom convention tường minh:** quy ước được truyền trực tiếp cho lần tạo observation qua API tương ứng.

Với overload nhận custom, default, context supplier và registry, thứ tự lựa chọn được minh họa là:

```text
Có custom được truyền trực tiếp?
    có  → dùng custom phù hợp với hợp đồng instrumentation
    không
       ↓
Có global hỗ trợ context?
    có  → dùng global được registry chọn
    không
       ↓
Dùng default của instrumentation
```

Đây là **chọn một quy ước**, không phải tự chạy default rồi chồng toàn bộ nhãn của global rồi chồng custom. Nếu custom muốn giữ nhãn của một lớp quy ước mặc định, nó phải kế thừa/gọi logic đó có chủ đích.

Thứ tự custom → global phù hợp → default được mô tả trong [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html). Phần thực hành kiểm chứng trực tiếp cơ chế này trên Micrometer 1.13.0.

### 4.1. Tên truyền vào factory đơn giản có thể bị global convention phù hợp thay thế

Đừng mặc định rằng:

```java
Observation.createNotStarted("literal.checkout", () -> context, registry);
```

luôn giữ nguyên tên `literal.checkout` bất kể cấu hình registry.

Trong phép chạy của bài, registry đã có một `GlobalObservationConvention<CheckoutContext>` phù hợp. Factory nhận tên trực tiếp vẫn chọn quy ước toàn cục cho context đó; kết quả là tên `regional.checkout` và các nhãn do global cung cấp.

Vì vậy cần phân biệt **truyền một tên làm mặc định** với **truyền một convention tùy chỉnh tường minh**. Kiểm tra overload và cấu hình thực tế, không suy luận từ việc chỉ thấy một chuỗi tên ở nơi tạo observation.

### 4.2. Tránh nhiều global convention cùng tranh một context

Nếu nhiều global convention đều hỗ trợ cùng context, đừng kỳ vọng các bộ nhãn tự hợp nhất. Việc registry/framework chọn và sắp xếp các ứng viên phải được xác minh trong cấu hình cụ thể.

Thiết kế dễ kiểm soát hơn là giữ ranh giới hỗ trợ rõ ràng hoặc chủ động cung cấp convention tường minh tại điểm instrumentation. Không dùng thứ tự xuất hiện ngẫu nhiên của bean làm một hợp đồng tên metrics không được kiểm thử.

### 4.3. Một bean thông thường chưa chứng minh instrumentation đã sử dụng nó

Khai báo một lớp implements `ObservationConvention` hoặc một bean của kiểu đó không đủ để khẳng định mọi observation trong Spring Boot sẽ đổi tên.

Cần biết convention được nối bằng cách nào:

- Truyền trực tiếp vào API tạo observation.
- Đăng ký dưới vai trò global convention.
- Cung cấp đúng kiểu mở rộng mà instrumentation HTTP/database/thư viện đang tìm.

Ví dụ `CheckoutConvention` nghiệp vụ không tự thay thế quy ước của HTTP server chỉ vì hai lớp cùng implements một interface gốc.

## 5. Giữ mã nghiệp vụ độc lập với quy ước quan sát

Trong chương trình thực hành, phần nghiệp vụ chỉ cập nhật `context.result` rồi có thể ném lỗi. Các quy ước phụ trách:

- Chọn tên ổn định.
- Chuẩn hóa channel cho metadata.
- Lấy result từ context.
- Phân loại mã đơn hàng vào high cardinality.
- Bổ sung nhãn thuộc vùng triển khai hoặc cấp dịch vụ.

Các phương thức của convention nên nhẹ và có thể được gọi lại mà không tạo tác dụng phụ. Tránh gọi mạng, truy vấn database, sinh một UUID mới hoặc thay đổi trạng thái nghiệp vụ trong `getLowCardinalityKeyValues`.

Convention có thể là đối tượng dùng chung cho nhiều lần gọi. Không giữ `currentOrderId` hay kết quả của yêu cầu gần nhất vào trường của convention. Dữ liệu từng lần thực hiện nằm trong context; cấu hình bất biến, chẳng hạn một tên vùng triển khai, có thể là dữ liệu của convention.

Đổi cách quan sát không nên làm phương thức tạo đơn hàng được gọi thêm lần nữa, cũng không nên thay đổi kết quả nghiệp vụ. Một observation có thể không hoạt động do cấu hình, nhưng nghiệp vụ vẫn phải có đường thực thi độc lập.

## 6. Ví dụ Java chạy được

### 6.1. Chuẩn bị

Cần JDK 17 trở lên và hai JAR cùng phiên bản:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

Đặt chúng vào thư mục `lib/` cạnh file Java. Có thể lấy từ Maven Central hoặc cache của công cụ build. Phiên bản này cố định cho ví dụ độc lập; không phải yêu cầu ghi đè dependency management của Spring Boot.

```text
convention-demo/
├── ObservationConventionDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 6.2. Mã nguồn đầy đủ

Lưu file `ObservationConventionDemo.java`:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.Map;
import java.util.TreeMap;

public class ObservationConventionDemo {
    static final class CheckoutContext extends Observation.Context {
        final String channel;
        final String orderId;
        String result = "pending";

        CheckoutContext(String channel, String orderId) {
            this.channel = channel;
            this.orderId = orderId;
        }
    }

    static class DefaultCheckoutConvention
            implements ObservationConvention<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public String getName() {
            return "checkout.process";
        }

        @Override
        public String getContextualName(CheckoutContext context) {
            return "process checkout";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            String channel = switch (context.channel == null ? "" : context.channel) {
                case "web" -> "web";
                case "store" -> "store";
                default -> "other";
            };
            return KeyValues.of("channel", channel, "result", context.result);
        }

        @Override
        public KeyValues getHighCardinalityKeyValues(CheckoutContext context) {
            return KeyValues.of("order.id", context.orderId);
        }
    }

    static final class RegionalCheckoutConvention
            extends DefaultCheckoutConvention
            implements GlobalObservationConvention<CheckoutContext> {
        @Override
        public String getName() {
            return "regional.checkout";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            return super.getLowCardinalityKeyValues(context)
                    .and("deployment.region", "lab");
        }
    }

    static final class ShopCheckoutConvention extends DefaultCheckoutConvention {
        @Override
        public String getName() {
            return "shop.checkout";
        }

        @Override
        public String getContextualName(CheckoutContext context) {
            return "checkout via shop";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            return super.getLowCardinalityKeyValues(context)
                    .and("tier", "standard");
        }
    }

    static final class ConsoleHandler
            implements ObservationHandler<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public void onStart(CheckoutContext context) {
            System.out.println("START name=" + context.getName()
                    + " low=" + tags(context.getLowCardinalityKeyValues()));
        }

        @Override
        public void onStop(CheckoutContext context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            System.out.println("STOP name=" + context.getName()
                    + " contextual=" + context.getContextualName());
            System.out.println("LOW " + tags(context.getLowCardinalityKeyValues()));
            System.out.println("HIGH " + tags(context.getHighCardinalityKeyValues()));
            System.out.println("ERROR " + error);
        }
    }

    static String tags(KeyValues keyValues) {
        Map<String, String> sorted = new TreeMap<>();
        for (KeyValue keyValue : keyValues) {
            sorted.put(keyValue.getKey(), keyValue.getValue());
        }
        return sorted.toString();
    }

    static void run(ObservationRegistry registry, String label,
                    ObservationConvention<CheckoutContext> custom,
                    String channel, String orderId, boolean fail) {
        System.out.println("CASE " + label);
        CheckoutContext context = new CheckoutContext(channel, orderId);
        Observation observation = Observation.createNotStarted(
                custom, new DefaultCheckoutConvention(), () -> context, registry);
        try {
            observation.observe((Runnable) () -> {
                context.result = fail ? "failure" : "success";
                if (fail) {
                    throw new IllegalStateException("payment refused");
                }
            });
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(new ConsoleHandler());

        run(registry, "default", null, "web", "demo-101", false);

        registry.observationConfig()
                .observationConvention(new RegionalCheckoutConvention());
        run(registry, "global", null, "store", "demo-102", false);

        run(registry, "explicit", new ShopCheckoutConvention(),
                "unexpected-input", "demo-103", true);

        System.out.println("CASE direct-name");
        CheckoutContext direct = new CheckoutContext("web", "demo-104");
        Observation.createNotStarted("literal.checkout", () -> direct, registry)
                .observe((Runnable) () -> direct.result = "success");
    }
}
```

Các mã `demo-101` đến `demo-104` là định danh giả lập. `ConsoleHandler` chỉ hiển thị metadata trong context, không cấu hình xuất metrics hay traces.

Hàm `tags` sắp xếp khóa bằng `TreeMap` để stdout có thứ tự dễ so sánh; đây là định dạng hiển thị của bài, không phải định dạng của một backend cụ thể.

### 6.3. Biên dịch và chạy

Trong PowerShell:

```powershell
javac --release 17 -cp "lib/*" ObservationConventionDemo.java
java -cp ".;lib/*" ObservationConventionDemo
```

Trên Linux/macOS, dùng dấu `:` giữa các mục classpath:

```bash
javac --release 17 -cp "lib/*" ObservationConventionDemo.java
java -cp ".:lib/*" ObservationConventionDemo
```

Chương trình đã được biên dịch với `--release 17`, chạy trên OpenJDK 24.0.2 cùng Micrometer 1.13.0. Stdout thu được:

```text
CASE default
START name=checkout.process low={channel=web, result=pending}
STOP name=checkout.process contextual=process checkout
LOW {channel=web, result=success}
HIGH {order.id=demo-101}
ERROR none
CASE global
START name=regional.checkout low={channel=store, deployment.region=lab, result=pending}
STOP name=regional.checkout contextual=process checkout
LOW {channel=store, deployment.region=lab, result=success}
HIGH {order.id=demo-102}
ERROR none
CASE explicit
START name=shop.checkout low={channel=other, result=pending, tier=standard}
STOP name=shop.checkout contextual=checkout via shop
LOW {channel=other, result=failure, tier=standard}
HIGH {order.id=demo-103}
ERROR IllegalStateException
CAUGHT payment refused
CASE direct-name
START name=regional.checkout low={channel=web, deployment.region=lab, result=pending}
STOP name=regional.checkout contextual=process checkout
LOW {channel=web, deployment.region=lab, result=success}
HIGH {order.id=demo-104}
ERROR none
```

### 6.4. Đối chiếu bốn trường hợp

| Trường hợp | Cấu hình tại thời điểm tạo | Kết quả |
| --- | --- | --- |
| `default` | Không truyền custom, chưa đăng ký global | `checkout.process`, nhãn từ default |
| `global` | Không truyền custom, global hỗ trợ context đã đăng ký | `regional.checkout`, có `deployment.region=lab` |
| `explicit` | Truyền `ShopCheckoutConvention` dù global vẫn tồn tại | `shop.checkout`, có `tier=standard` |
| `direct-name` | Dùng factory nhận tên `literal.checkout` và context checkout | Global phù hợp vẫn tạo tên `regional.checkout` |

Ở trường hợp `explicit`, không có nhãn `deployment.region`. Đây là bằng chứng metadata của global không tự chồng lên custom. `ShopCheckoutConvention` gọi `super` của `DefaultCheckoutConvention`, không gọi `RegionalCheckoutConvention`.

Đầu vào `unexpected-input` được quy ước thành `channel=other`. Nhãn `result=failure` xuất hiện khi công việc thất bại; lỗi vẫn được `observe` truyền ra và phần demo bắt lại, tạo dòng `CAUGHT payment refused`.

Dòng `ERROR none` trong stdout chỉ là cách handler của ví dụ hiển thị việc context chưa có lỗi. Nó không phải một nhãn lỗi bắt buộc của Micrometer.

### 6.5. Vì sao START thấy pending còn STOP thấy success/failure?

Ban đầu, mỗi context có `result=pending`. Trong lambda nghiệp vụ, chương trình đổi nó thành kết quả cuối cùng.

Với đường thực thi Micrometer 1.13.0 đã kiểm chứng, nhãn từ convention được cập nhật theo context ở các mốc vòng đời liên quan; handler trong ví dụ nhìn thấy kết quả cuối ở `onStop`.

Điều đó không có nghĩa mọi đầu ra đã được tạo ở đầu công việc sẽ tự đổi nhãn sau này. Một handler có thể chốt dữ liệu từ lúc bắt đầu, handler khác đọc khi kết thúc. Chẳng hạn, một phép đo công việc đang hoạt động được tạo lúc start không nên bị mặc định là sẽ mang bộ nhãn của phép đo hoàn tất.

Vì vậy:

- Dữ liệu đầu vào đã biết như channel cần có trước khi bắt đầu.
- Dữ liệu chỉ biết cuối công việc như kết quả cần được xác định đúng thời điểm.
- Không dùng kết quả cuối để tính một tên observation thay đổi trong quá trình chạy.
- Khi tùy chỉnh một instrumentation có sẵn, kiểm tra mốc mà handler của nó đọc metadata.

Đừng gọi trực tiếp các getter của convention rồi coi đó là bằng chứng tích hợp: phải kiểm tra metadata trong observation tại thời điểm handler thực sự sử dụng.

## 7. Bổ sung nhãn và thay thế nhãn là hai thay đổi khác nhau

### 7.1. Muốn giữ mặc định thì gọi super có chủ đích

Trong custom convention của chương trình:

```java
@Override
public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
    return super.getLowCardinalityKeyValues(context)
            .and("tier", "standard");
}
```

Kết quả giữ `channel`, `result` của lớp mặc định và bổ sung `tier`.

Nếu thay bằng:

```java
@Override
public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
    return KeyValues.of("tier", "standard");
}
```

thì phương thức không còn trả lại `channel` và `result` từ lớp mặc định. Đây là một quyết định thay thế bộ nhãn low cardinality, không chỉ là cách viết khác để thêm một nhãn.

Tương tự, override `getHighCardinalityKeyValues` và trả một bộ mới có thể bỏ các trường chi tiết của lớp cha. Nếu chỉ override phương thức low như ví dụ chính, phương thức high kế thừa vẫn giữ `order.id`.

Khi dùng `KeyValues.and(...)`, sử dụng giá trị được trả về, chẳng hạn return trực tiếp chuỗi gọi như ở trên. Không gọi `values.and(...)` rồi bỏ kết quả, sau đó mặc định biến `values` đã được cập nhật theo ý muốn.

### 7.2. Giữ hợp đồng nhãn của instrumentation có sẵn

Một quy ước mặc định HTTP có thể đã cung cấp các chiều phân loại mà dashboard và cảnh báo đang dùng. Nếu thay toàn bộ bộ nhãn chỉ để thêm `application.area`, ta có thể vô tình bỏ các chiều cần thiết đó.

Trước khi thay quy ước:

1. Xác định tên và nhãn đang là hợp đồng sử dụng của hệ thống.
2. Phân biệt phần muốn thêm, phần muốn đổi và phần thật sự muốn bỏ.
3. Giữ tập khóa low cardinality nhất quán giữa các lần thực hiện của cùng loại công việc.
4. Kiểm tra cả thành công, lỗi và dữ liệu đầu vào không như mong đợi.

Nếu thiếu giá trị, chọn chính sách rõ ràng: một giá trị hữu hạn như `unknown`, hoặc bỏ trường chi tiết khi hợp đồng cho phép. Không trả về `null` tùy tiện cho khóa/giá trị rồi chờ backend tự quyết định.

### 7.3. Metadata dùng chung cho mọi convention cần một điểm bổ sung riêng

Nếu vùng triển khai phải có ở mọi observation phù hợp dù người dùng chọn custom hay global, chỉ thêm nó trong một global convention có thể chưa đủ: custom tường minh có thể được ưu tiên.

Một `ObservationFilter` là lựa chọn để bổ sung metadata tại giai đoạn lọc context trước các callback kết thúc. Ví dụ đoạn cấu hình cho registry đã có:

```java
registry.observationConfig().observationFilter(context ->
        context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.environment", "lab")));
```

Đây là đoạn trích, cần import `io.micrometer.common.KeyValue`. Bộ lọc là một cơ chế khác, không làm thay đổi thứ tự lựa chọn convention.

Vì bộ lọc này áp dụng ở mốc kết thúc, không giả định handler ở `onStart` đã nhìn thấy nhãn vừa bổ sung. Nếu metadata bắt buộc phải có khi bắt đầu, thiết kế điểm cung cấp metadata tương ứng thay vì chỉ thêm một bộ lọc muộn.

Cũng không nhầm với `MeterFilter`: nó tác động ở tầng Micrometer Metrics; không phải cơ chế đổi tên/nhãn chung cho cả observation và tracing.

## 8. Đưa convention vào Spring Boot Actuator

### 8.1. Dùng đúng registry và đúng điểm mở rộng

Trong ứng dụng Spring Boot 3.3, dùng `ObservationRegistry` được inject để giữ các handler và tùy biến do Boot cấu hình. Nếu tự tạo registry riêng trong service, các bean hoặc convention ở registry được quản lý không tự xuất hiện ở registry mới.

Boot đăng ký bean `GlobalObservationConvention` vào registry của nó. Nếu cần convention tường minh cho nghiệp vụ riêng, mã instrumentation phải nhận và truyền convention đó vào API tạo observation, như phương thức `run` trong chương trình.

Các quy tắc đăng ký bean, registry và nhãn low/high của tích hợp Boot được mô tả trong [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Việc “đã có bean” chỉ là một phần của quá trình kiểm tra. Còn phải xác minh loại context, điểm sử dụng convention, điều kiện hỗ trợ và đầu ra thực tế.

### 8.2. Ví dụ thêm nhãn cho Spring MVC mà giữ mặc định

Với HTTP server trong Spring MVC, có điểm mở rộng chuyên biệt `ServerRequestObservationConvention` thuộc package servlet `org.springframework.http.server.observation`.

Đoạn cấu hình dưới dành cho một ứng dụng Spring Boot 3.3 có Spring MVC và Actuator. Nó thêm nhãn cố định `application.area=shop` và giữ bộ nhãn low cardinality mặc định:

```java
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationContext;
import org.springframework.http.server.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class HttpObservationConfig {
    @Bean
    ServerRequestObservationConvention serverRequestObservationConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {
                return super.getLowCardinalityKeyValues(context)
                        .and("application.area", "shop");
            }
        };
    }
}
```

Đây là file cấu hình để đặt trong package được ứng dụng quét, không phải một chương trình console độc lập. `super.getLowCardinalityKeyValues(context)` là phần giữ hợp đồng mặc định; bỏ nó để trả riêng nhãn mới là một thay đổi khác.

Nếu chỉ muốn đổi tên observation HTTP server theo hỗ trợ của Boot:

```yaml
management:
  observations:
    http:
      server:
        requests:
          name: shop.http.requests
```

Không đồng thời thay tên ở nhiều điểm rồi suy đoán kết quả. Khi có thêm custom convention hoặc global convention, xác minh tên cuối cùng đang được sử dụng.

Theo tài liệu Boot, MVC và WebFlux có các convention HTTP tương ứng ở **hai package khác nhau**. Với WebFlux, package là `org.springframework.http.server.reactive.observation`; không sao chép nguyên import servlet vào ứng dụng reactive.

Tên HTTP mặc định, property đổi tên và điểm mở rộng thêm/thay nhãn được nêu trong [Spring Boot 3.3 — Metrics, Spring MVC và WebFlux](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 8.3. Nhãn chung có thể dùng cấu hình đơn giản hơn

Nếu nhu cầu chỉ là thêm một số nhãn môi trường hữu hạn cho observations của Boot, có thể dùng cấu hình chung:

```yaml
management:
  observations:
    key-values:
      deployment.environment: lab
      deployment.region: local
```

Không cần viết một convention mới chỉ để lặp lại giá trị cấu hình ở mọi loại công việc. Dùng convention khi cần quy tắc gắn với context hoặc một hợp đồng tên/nhãn cụ thể.

Ngược lại, không nhét mã đơn hàng lấy từ request vào cấu hình nhãn chung: giá trị theo từng lần thực hiện thuộc context và cần được phân loại theo cardinality phù hợp.

## 9. Cách kiểm chứng một thay đổi convention

Nên kiểm tra theo ba tầng:

| Tầng | Câu hỏi cần trả lời |
| --- | --- |
| Hàm quy ước | Với một context mẫu, tên và các cặp khóa–giá trị được trả về có đúng không? |
| Observation thực tế | Quy ước nào được chọn? Handler thấy dữ liệu gì ở mốc sử dụng? |
| Đầu ra tích hợp | Timer/span thực có tên, nhãn và số lượng như dự kiến không? |

Chương trình console của bài kiểm chứng tầng observation thực tế qua handler. Nó chưa chứng minh đã có timer hoặc span trong một ứng dụng Spring đang chạy.

Với một thay đổi triển khai thực, cần kiểm tra thêm:

- Context đúng loại và registry đúng đối tượng được cấu hình.
- Khi không truyền custom, global phù hợp và mặc định dự phòng có kết quả đúng.
- Khi có custom, metadata của nó không vô tình mất các nhãn cần giữ.
- Đầu vào lạ/`null` có chính sách chuẩn hóa rõ ràng.
- Kết quả cuối của nhánh thành công và lỗi được gắn ở mốc phù hợp.
- Không tạo thêm tên hoặc nhãn low cardinality theo từng định danh.
- Truy vấn/dashboard/cảnh báo được cập nhật nếu đổi hợp đồng tên/nhãn.

Micrometer cung cấp `micrometer-observation-test` và `TestObservationRegistry` để kiểm tra observation và metadata trong kiểm thử tự động; xem [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

Không chỉ kiểm tra `new MyConvention().getName()`: một phương thức trả đúng chuỗi vẫn không giúp gì nếu convention chưa bao giờ được chọn bởi instrumentation.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng sửa |
| --- | --- | --- |
| Có lớp convention nhưng tên không đổi | Chưa nối vào registry hoặc instrumentation | Xác định cách đăng ký/truyền convention |
| Global không được dùng | Context không khớp hoặc có custom tường minh | Kiểm tra loại context và thứ tự ưu tiên |
| Tên truyền vào factory bị đổi | Global phù hợp được chọn | Đối chiếu cấu hình thay vì chỉ nhìn chuỗi ở factory |
| Thêm một nhãn nhưng mất các nhãn mặc định | Override trả bộ mới, không giữ super | Phân biệt thêm và thay thế |
| Console có HIGH nên tưởng metrics cũng có | Handler console đọc cả hai nhóm | Kiểm tra handler metrics/tracing thực tế |
| Số chuỗi tăng theo số đơn hàng | Định danh được dùng trong tên/nhãn low | Giữ tên ổn định, phân loại lại dữ liệu chi tiết |
| Cùng công việc có các bộ khóa không nhất quán | Getter có nhiều nhánh bỏ khóa tùy tiện | Định nghĩa schema và giá trị thiếu hữu hạn |
| START chưa có kết quả cuối | Kết quả chỉ xuất hiện sau nghiệp vụ | Kiểm tra mốc handler đọc metadata |
| Getter tạo tác dụng phụ nhiều lần | Dùng convention làm nơi chạy nghiệp vụ | Chỉ tính metadata từ context/cấu hình |
| MVC không nhận cấu hình convention mong đợi | Sai kiểu mở rộng hoặc nhầm package reactive | Chọn đúng convention của instrumentation đang dùng |

## 11. Bài tập tự kiểm tra

**Tình huống 1:** Registry có global convention hỗ trợ checkout. Lần gọi lại truyền `ShopCheckoutConvention` tường minh. Tên và nhãn vùng triển khai sẽ thế nào?

Trong chương trình, tên là `shop.checkout`. Không có `deployment.region` của global, vì custom được chọn và chỉ kế thừa nhãn của lớp mặc định. Muốn nhãn vùng có trong cả hai đường phải thiết kế điểm bổ sung phù hợp, không trông chờ các convention tự hợp nhất.

**Tình huống 2:** Đổi `ShopCheckoutConvention.getLowCardinalityKeyValues` thành chỉ trả `KeyValues.of("tier", "standard")`. Nhãn nào mất?

Các nhãn `channel`, `result` do phương thức low của lớp cha tạo không còn được trả về. Nhãn high `order.id` vẫn đến từ phương thức high kế thừa, nếu các phần khác giữ nguyên.

**Tình huống 3:** Tạo một nghìn context với mã đơn khác nhau nhưng cùng channel và result. Metadata low có cần một nghìn giá trị khác nhau không?

Không theo thiết kế trong bài. Mã đơn nằm ở nhóm high; bộ low chỉ phản ánh các chiều hữu hạn đã định nghĩa. Nếu đưa mã đơn sang low, thiết kế đó đã thay đổi dù tên getter vẫn chứa chữ “LowCardinality”.

**Tình huống 4:** Chương trình đổi tên bằng convention nhưng dashboard vẫn dùng tên cũ. Có thể kết luận dữ liệu không được ghi không?

Chưa thể. Kiểm tra tên thực trong đầu ra và truy vấn đang sử dụng. Đổi tên/nhãn là một thay đổi hợp đồng dữ liệu quan sát, cần được kiểm chứng cùng các nơi tiêu thụ.

**Thực hành với mã nguồn:**

- Thay một đầu vào channel bằng `null` và kiểm tra nó được nhóm thành `other`.
- Bỏ đăng ký global để so kết quả của factory nhận tên trực tiếp.
- Giữ global nhưng truyền custom, kiểm tra sự khác nhau của hai bộ nhãn.
- Thêm một thuộc tính vào `CheckoutContext` nhưng không ánh xạ trong convention; kiểm tra nó không tự trở thành nhãn.
- Kiểm tra cùng một quy ước trên cả nhánh thành công và nhánh lỗi.

Một convention tốt cung cấp tên ổn định, schema nhãn rõ ràng và cách chuẩn hóa có thể kiểm chứng. Nó giúp dữ liệu quan sát nhất quán trong khi vòng đời và kết quả nghiệp vụ vẫn được quản lý ở đúng nơi.
