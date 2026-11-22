# Kiểm tra hợp lệ và phát hiện dữ liệu không được liên kết qua BindHandler trong Spring Boot

## 1. Vì sao cần kiểm tra sâu hơn một lần bind thông thường?

Spring Boot cho phép đọc cấu hình từ nhiều nguồn: `application.yml`, `application.properties`, biến môi trường, Java system properties, command-line arguments và các `PropertySource` khác. Với `@ConfigurationProperties`, ứng dụng có thể ánh xạ nhóm thuộc tính này sang một Java class hoặc record có kiểu rõ ràng.

Ví dụ:

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

Nếu mọi thứ phù hợp, Binder chuyển `threads` thành `int`, `timeout` thành `Duration` và `enabled` thành `boolean`.

Tuy nhiên, chỉ bind được dữ liệu chưa đảm bảo cấu hình đúng:

**Tình huống A — Giá trị đúng kiểu nhưng sai nghiệp vụ**

~~~yaml
demo:
  worker:
    threads: 0
    timeout: 0s
    enabled: true
~~~

`0` vẫn là số nguyên hợp lệ; `0s` vẫn có thể chuyển thành `Duration.ZERO`. Nhưng cả hai có thể không hợp lệ cho một worker pool.

**Tình huống B — Người triển khai gõ sai tên thuộc tính**

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
    threds: 12
~~~

`threds` không phải tên field của record `WorkerSettings`. Một cơ chế binding thông thường có thể bỏ qua thuộc tính không được ánh xạ này, khiến người triển khai tưởng đã thiết lập 12 threads trong khi ứng dụng dùng 4.

**Tình huống C — Sai kiểu ngay khi chuyển đổi**

~~~yaml
demo:
  worker:
    threads: many
    timeout: 5s
~~~

`many` không thể chuyển thành `int`, vì vậy binding có thể thất bại trước khi kiểm tra nghiệp vụ.

Spring Boot cung cấp giao diện **`BindHandler`** và các triển khai chuyên biệt để can thiệp vào vòng đời binding. Hai handler quan trọng đối với bài này là:

- **`ValidationBindHandler`:** áp dụng các `Validator` lên kết quả được bind, giúp phát hiện giá trị sai quy tắc.
- **`NoUnboundElementsBindHandler`:** phát hiện các thuộc tính nằm dưới root cấu hình nhưng không được liên kết vào target.

Hai cơ chế giải quyết **hai loại lỗi khác nhau**; trong một số trường hợp có thể kết hợp chúng để xây dựng quy trình cấu hình nghiêm ngặt hơn.

## 2. Phân biệt bốn tình trạng của một property

| Tình trạng | Ví dụ | Vấn đề chính |
| --- | --- | --- |
| Bind thành công và hợp lệ | `threads=4`, điều kiện ≥ 1 | Không có lỗi |
| Bind được nhưng vi phạm điều kiện | `threads=0` với quy tắc ≥ 1 | Validation |
| Không chuyển được kiểu | `threads=many`, đích `int` | Conversion/binding failure |
| Thuộc tính không được bind | `threds=12` nhưng class chỉ có `threads` | Unbound/unknown property |

Cũng cần phân biệt tình trạng **thiếu hẳn một thuộc tính bắt buộc**. Ví dụ không có `demo.worker.timeout` không nhất thiết tạo ra một *unbound element*, vì không có element đầu vào nào để báo là đã bị bỏ sót. Việc phát hiện thuộc tính bắt buộc nên thực hiện bằng kiểu tham chiếu phù hợp, validation hoặc kiểm tra hợp đồng cấu hình.

Các cơ chế xử lý:

| Mục tiêu | Công cụ thường dùng |
| --- | --- |
| Phát hiện sai kiểu | Binder mặc định và conversion |
| Phát hiện giá trị đúng kiểu nhưng sai điều kiện | `ValidationBindHandler` hoặc `@Validated` với Bean Validation |
| Phát hiện khóa cấu hình dưới root không được liên kết | `NoUnboundElementsBindHandler` |
| Quan sát những property được bind thành công | `BoundPropertiesTrackingBindHandler` hoặc custom handler |
| Đặt default khi thiếu thuộc tính | `@DefaultValue`, default trong code hoặc placeholder phù hợp |
| Tạo binding có cấu trúc | `Binder`/`@ConfigurationProperties` |

**Không dùng một handler để thay thế hoàn toàn tất cả các cơ chế còn lại.** Ví dụ `NoUnboundElementsBindHandler` không quyết định số threads phải dương, còn `ValidationBindHandler` không tự suy luận rằng mỗi khóa typo đều phải bị từ chối.

## 3. `BindHandler` nằm ở đâu trong kiến trúc Binder?

Khi gọi `Binder` trực tiếp, Spring Boot cung cấp overload nhận handler:

~~~java
<T> BindResult<T> bind(
        String name,
        Bindable<T> target,
        BindHandler handler
);
~~~

Ý nghĩa:

- `name` là root prefix, ví dụ `"demo.worker"`.
- `target` mô tả kiểu Java cần bind, ví dụ `Bindable.of(WorkerSettings.class)`.
- `handler` nhận các callback trong quá trình bind.
- `BindResult<T>` cho biết có bind được một kết quả hay không và cho phép truy xuất kết quả theo API của nó.

Ví dụ minh họa:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

Binder binder = /* Binder lấy từ các nguồn cấu hình */;

BindResult<WorkerSettings> result =
        binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                BindHandler.DEFAULT
        );

WorkerSettings settings = result.get();
~~~

`BindHandler.DEFAULT` là handler không bổ sung quy tắc đặc biệt. Nếu không có dữ liệu bind được, `BindResult#get()` có thể báo thiếu kết quả; khi muốn xử lý tùy chọn, nên dùng API `isBound()`, `orElse(...)` hoặc phương thức tương ứng của `BindResult`.

Với ứng dụng Spring Boot dùng `@ConfigurationProperties` thông thường, framework đã có quy trình binding riêng. Việc **tự tạo `Binder`** hữu ích khi viết thư viện, kiểm thử cấu hình độc lập, bind một namespace đặc biệt hoặc muốn áp dụng handler cho đúng một lần bind.

Không cần thay thế toàn bộ cơ chế `@ConfigurationProperties` của ứng dụng chỉ để bật validation hay từ chối unknown fields.

## 4. Những callback của `BindHandler`

`BindHandler` là một giao diện callback. Trong Spring Boot 3.3, các method quan trọng gồm:

| Callback | Khi nào được gọi | Công dụng |
| --- | --- | --- |
| `onStart(...)` | Trước khi bind một phần tử | Quan sát tên/target, điều chỉnh bindable nếu thật sự cần |
| `onSuccess(...)` | Khi một phần tử bind thành công | Ghi nhận kết quả, bổ sung xử lý hoặc validation |
| `onCreate(...)` | Khi một instance mới sắp được trả về trong trường hợp kết quả chưa được bind | Xử lý instance do Binder tạo |
| `onFailure(...)` | Khi một bước binding gặp lỗi | Báo lại, biến đổi hoặc trong trường hợp đặc biệt xử lý lỗi |
| `onFinish(...)` | Khi binding của một phần tử kết thúc bình thường | Thực hiện xử lý cuối của bước bind |

Giao diện có callback với các đối tượng như:

~~~java
ConfigurationPropertyName name
Bindable<?> target
BindContext context
Object result
Exception error
~~~

Trong đó:

- `ConfigurationPropertyName` đại diện tên cấu hình theo mô hình của Spring Boot.
- `Bindable<?>` đại diện target type và thông tin binding liên quan.
- `BindContext` mang trạng thái/thông tin của lần binding đang diễn ra.
- `result` là kết quả ở thời điểm callback; có thể là object trung gian hoặc object cuối.
- `error` là nguyên nhân khi binding không thành công.

**Không giả định mọi callback chỉ chạy một lần cho root.** Binder có thể đi qua các trường, phần tử collection và nested object, nên callback có thể xuất hiện ở nhiều cấp tên thuộc tính.

Ngoài ra, `onFinish` không phải một khối `finally` Java chạy bất kể mọi lỗi: theo hợp đồng API, nó không được gọi trong một số đường đi khi binding thất bại, kể cả khi một handler xử lý lỗi qua `onFailure`. Không nên dùng nó như phương thức duy nhất để giải phóng tài nguyên quan trọng.

## 5. `AbstractBindHandler` và mô hình handler lồng nhau

Thay vì tự triển khai mọi method của `BindHandler`, có thể kế thừa `AbstractBindHandler`:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindHandler;

BindHandler observingHandler =
        new AbstractBindHandler(BindHandler.DEFAULT) {
            // Override những callback thực sự cần thiết.
        };
~~~

`AbstractBindHandler` hỗ trợ cơ chế **parent/delegate**. Khi cần thêm logic vào handler hiện tại, ta truyền handler cũ làm parent:

~~~text
Outer Handler
      │
      ▼
Parent Handler
      │
      ▼
BindHandler.DEFAULT
~~~

Điều này đặc biệt hữu ích khi ghép nhiều trách nhiệm:

- Một handler làm validation.
- Một handler phát hiện unbound elements.
- Một handler do dự án thêm để ghi metric hoặc audit tên property.

Cách ghép handler ảnh hưởng đến thứ tự các callback và lỗi nào được báo trước khi có nhiều lỗi đồng thời. Không nên xem việc đổi thứ tự hai handler là luôn tương đương, nhất là nếu custom handler có `onFailure` nuốt exception hoặc thay đổi result.

Một nguyên tắc an toàn: **handler quan sát nên delegate bình thường; handler thay đổi kết quả hoặc bỏ qua lỗi chỉ nên dùng khi có yêu cầu cụ thể và test rõ ràng**.

## 6. `ValidationBindHandler`: áp dụng validator sau binding

Class:

~~~java
org.springframework.boot.context.properties.bind.validation.ValidationBindHandler
~~~

Nó là một `BindHandler` được thiết kế để dùng các `org.springframework.validation.Validator` kiểm tra kết quả bind.

Hai constructor tiêu biểu:

~~~java
new ValidationBindHandler(validator);

new ValidationBindHandler(parentHandler, validator);
~~~

Ở đây `validator` là một hoặc nhiều Spring `Validator`, không phải chỉ là một tên annotation.

Ví dụ:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class WorkerSettingsValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return WorkerSettings.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        WorkerSettings settings = (WorkerSettings) target;

        if (settings.threads() < 1) {
            errors.rejectValue(
                    "threads",
                    "worker.threads.invalid",
                    "threads must be at least 1"
            );
        }

        if (settings.timeout() == null
                || settings.timeout().isZero()
                || settings.timeout().isNegative()) {
            errors.rejectValue(
                    "timeout",
                    "worker.timeout.invalid",
                    "timeout must be positive"
            );
        }
    }
}
~~~

Đây là một **Spring Validator tự viết**, kiểm tra object sau khi giá trị đã được chuyển thành các kiểu Java. Nó không yêu cầu developer phải parse chuỗi `"5s"` bằng tay.

Một ví dụ dùng handler:

~~~java
BindHandler handler = new ValidationBindHandler(
        new WorkerSettingsValidator()
);

WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        handler
).get();
~~~

Nếu `threads=0` hoặc `timeout=0s`, validator có thể tạo lỗi; `ValidationBindHandler` đưa lỗi đó vào luồng binding, làm lời gọi thất bại theo hợp đồng validation.

Nếu `threads=many`, quá trình chuyển sang `int` có thể lỗi trước khi validator nhận được object hoàn chỉnh. Đây là **binding/conversion failure**, không phải lỗi “threads phải lớn hơn 0”.

## 7. Mô hình cấu hình dùng trong các ví dụ

Để các ví dụ tiếp theo nhất quán, sử dụng record:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

Khi dùng Binder thủ công, record này **không bắt buộc** có `@ConfigurationProperties`, vì lời gọi `binder.bind("demo.worker", Bindable.of(WorkerSettings.class), handler)` đã truyền root prefix và type rõ ràng.

Còn nếu sử dụng bean `@ConfigurationProperties` thông thường, có thể khai báo:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

Với Spring Boot 3.x, record có canonical constructor phù hợp có thể được constructor-bound khi đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

**Hai ví dụ có cùng schema nhưng khác đường đi:** một ví dụ **gọi Binder trực tiếp**, một ví dụ **để Spring Boot quản lý bean cấu hình**. Phải phân biệt hai đường đi này khi muốn kích hoạt validation và handler.

## 8. Tạo Binder trực tiếp từ một MapPropertySource

Để tập trung vào hành vi handler, ví dụ đơn giản nhất là dùng một nguồn dữ liệu độc lập có thể liệt kê các khóa.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> values = new LinkedHashMap<>();

values.put("demo.worker.threads", "4");
values.put("demo.worker.timeout", "5s");
values.put("demo.worker.enabled", "true");

MapPropertySource propertySource =
        new MapPropertySource("example", values);

Binder binder = new Binder(
        ConfigurationPropertySources.from(propertySource)
);
~~~

Giải thích:

1. `MapPropertySource` là một Spring `PropertySource` chứa các cặp tên/giá trị.
2. `ConfigurationPropertySources.from(propertySource)` cung cấp adapter để Binder đọc chúng như `ConfigurationPropertySource`.
3. `new Binder(...)` tạo Binder cho đúng nguồn thử nghiệm đó.
4. Handler được truyền vào lời gọi `binder.bind(...)` sẽ được dùng cho một lần bind cụ thể.

Lợi ích của nguồn thử nghiệm riêng:

- Không vô tình lấy giá trị từ biến môi trường của máy.
- Tránh property khác của ứng dụng ảnh hưởng namespace đang kiểm tra.
- Dễ tạo từng trường hợp valid/invalid/unknown.
- Phù hợp cho unit test về hành vi Binder/handler mà không cần bật web server.

`Binder` có những constructor và overload khác, cùng phương thức `Binder.get(Environment)` trong các phiên bản thích hợp. Nhưng với bài học về handler, một nguồn Map rõ ràng giúp quan sát hành vi hơn.

## 9. Ví dụ dùng `ValidationBindHandler` từ đầu đến cuối

Giả sử có `WorkerSettings` và `WorkerSettingsValidator` từ các phần trên.

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

public final class ValidationDemo {

    public static void main(String[] args) {
        Map<String, Object> data = Map.of(
                "demo.worker.threads", "6",
                "demo.worker.timeout", "8s",
                "demo.worker.enabled", "true"
        );

        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("demo", data)
                )
        );

        BindHandler handler = new ValidationBindHandler(
                new WorkerSettingsValidator()
        );

        WorkerSettings settings = binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                handler
        ).get();

        System.out.println(settings.threads());
        System.out.println(settings.timeout());
    }
}
~~~

Khi các kiểu và class hỗ trợ có mặt trên classpath, kết quả minh họa là:

~~~text
6
PT8S
~~~

Thay:

~~~java
"demo.worker.threads", "0"
~~~

thì điều kiện `threads >= 1` bị vi phạm. Chương trình có thể nhận một exception do validation trong quá trình bind, thay vì một `WorkerSettings` hợp lệ.

Nếu thay:

~~~java
"demo.worker.threads", "many"
~~~

thì converter không thể tạo `int`, dù `WorkerSettingsValidator` có tồn tại. Hãy xem nguyên nhân lỗi để phân biệt **conversion** và **validation**.

## 10. `NoUnboundElementsBindHandler`: phát hiện khóa không được dùng

Class:

~~~java
org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler
~~~

Vai trò chính: **yêu cầu tất cả configuration properties dưới root đang bind đã được liên kết**.

Ví dụ nguồn:

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=12
~~~

Target:

~~~java
public record WorkerSettings(
        int threads,
        Duration timeout,
        boolean enabled
) {}
~~~

Ba khóa đầu có đích phù hợp. Khóa cuối `threds` là typo, không có component trong `WorkerSettings`.

Nếu bind với handler bình thường, tùy chính sách, typo có thể không khiến lời gọi thất bại. Nhưng:

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT
);
~~~

có thể phát hiện rằng vẫn còn `demo.worker.threds` không được liên kết và báo lỗi.

**Phạm vi kiểm tra:** handler này quan tâm những property **nằm dưới root của lần bind**. Nó không phải công cụ kiểm tra toàn bộ `Environment` của ứng dụng, và không tự phát hiện property bị thiếu nhưng chưa từng tồn tại trong nguồn.

Cần có nguồn cấu hình cho phép liệt kê/tìm các tên property một cách thích hợp. Một `MapPropertySource` có các tên rõ ràng là lựa chọn tốt để minh họa và test.

## 11. Ví dụ đầy đủ phát hiện unbound elements

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> data = new LinkedHashMap<>();
data.put("demo.worker.threads", "4");
data.put("demo.worker.timeout", "5s");
data.put("demo.worker.enabled", "true");
data.put("demo.worker.threds", "12"); // typo có chủ ý

Binder binder = new Binder(
        ConfigurationPropertySources.from(
                new MapPropertySource("demo", data)
        )
);

BindHandler strictHandler =
        new NoUnboundElementsBindHandler(BindHandler.DEFAULT);

WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        strictHandler
).get();
~~~

Nếu handler nhận diện thành công khóa `demo.worker.threds` là không được bind, lời gọi sẽ ném exception thay vì trả về `settings`.

Loại lỗi có thể xuất hiện trong chuỗi nguyên nhân là:

~~~text
UnboundConfigurationPropertiesException
~~~

Class này có API `getUnboundProperties()` để truy cập tập những `ConfigurationProperty` còn thừa. Ở tầng Binder, exception có thể được bọc trong `BindException` hoặc exception cấu hình khác. Đừng chỉ dựa vào việc class exception xuất hiện ở top-level; cần quan sát cause chain trong một test.

**Quan trọng:** `NoUnboundElementsBindHandler` không tìm lỗi chính tả bằng phép so sánh từ gần giống. Nó xác định **những property chưa được bind**. Việc thông báo có vẻ như “typo” là kết quả diễn giải của người đọc khi thấy tên `threds`.

## 12. So sánh một property bị bỏ qua và một property hoàn toàn thiếu

Hai trường hợp:

### 12.1. Property thừa

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.unused-setting=hello
~~~

`unused-setting` có mặt nhưng không có đích trong `WorkerSettings`. `NoUnboundElementsBindHandler` có thể báo rằng nó chưa được liên kết.

### 12.2. Property bắt buộc bị thiếu

~~~properties
demo.worker.threads=4
demo.worker.enabled=true
~~~

Không có `demo.worker.timeout`. Vì nó không tồn tại, không có key “thừa” để unbound handler liệt kê.

Nếu `timeout` là giá trị bắt buộc, hãy dùng một trong các cách:

- `@NotNull` trên `Duration timeout` cùng validation ở đường tạo bean thích hợp.
- Spring `Validator` trong `ValidationBindHandler` kiểm tra `settings.timeout() != null`.
- Kiểm tra bất biến trong constructor.
- Một cơ chế schema/configuration validation có quy tắc rõ ràng hơn.

**Kết luận:** “không có khóa dư” và “không thiếu khóa bắt buộc” là **hai điều kiện độc lập**.

## 13. Kết hợp `ValidationBindHandler` và `NoUnboundElementsBindHandler`

Với mục tiêu một lần bind vừa kiểm tra giá trị, vừa phát hiện property dư, có thể lồng handler theo cơ chế parent:

~~~java
BindHandler combined = new NoUnboundElementsBindHandler(
        new ValidationBindHandler(
                new WorkerSettingsValidator()
        )
);
~~~

Sau đó:

~~~java
WorkerSettings settings = binder.bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class),
        combined
).get();
~~~

Ý nghĩa:

1. `ValidationBindHandler` dùng `WorkerSettingsValidator` để kiểm tra giá trị bind được.
2. `NoUnboundElementsBindHandler` yêu cầu các thuộc tính trong root không bị bỏ sót.
3. Nếu cả hai nhóm điều kiện đạt, Binder trả về `WorkerSettings`.

Đây là một ví dụ ghép handler dựa trên các constructor public trong Spring Boot 3.x. Thứ tự wrapper có thể ảnh hưởng callback/lỗi được nhìn thấy trước khi có nhiều lỗi đồng thời. Không kỳ vọng mọi lỗi được gom thành một danh sách hoàn chỉnh sau một lượt bind.

Một cách lồng khác có thể dùng:

~~~java
BindHandler combined = new ValidationBindHandler(
        new NoUnboundElementsBindHandler(BindHandler.DEFAULT),
        new WorkerSettingsValidator()
);
~~~

Cả hai thể hiện các handler có quan hệ parent, nhưng thứ tự callback có thể khác. Nếu dự án yêu cầu thứ tự phát hiện chính xác hoặc format lỗi ổn định, viết test cho thứ tự đã chọn và phiên bản Spring Boot thực tế.

Không nên thay đổi thứ tự handler chỉ nhằm “làm một test đỏ trở thành xanh” nếu chưa hiểu ảnh hưởng đến callback và error propagation.

## 14. Ví dụ một utility bind nghiêm ngặt

Một utility có thể tái sử dụng cho nhóm cấu hình độc lập:

~~~java
package com.example.demo.config;

import java.util.Map;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

public final class StrictConfigLoader {

    private StrictConfigLoader() {}

    public static WorkerSettings load(Map<String, Object> properties) {
        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("strict-config", properties)
                )
        );

        BindHandler handler = new NoUnboundElementsBindHandler(
                new ValidationBindHandler(
                        new WorkerSettingsValidator()
                )
        );

        return binder.bind(
                "demo.worker",
                Bindable.of(WorkerSettings.class),
                handler
        ).get();
    }
}
~~~

Gọi:

~~~java
Map<String, Object> config = Map.of(
        "demo.worker.threads", "4",
        "demo.worker.timeout", "5s",
        "demo.worker.enabled", "true"
);

WorkerSettings worker = StrictConfigLoader.load(config);
~~~

Với giá trị hợp lệ và không dư property, kết quả mong đợi là record chứa 4, 5 giây và `true`.

Thay `threads=0` thì validation có thể thất bại.

Thêm `demo.worker.threds=12` thì unbound handler có thể phát hiện key dư.

Thay `threads=abc` thì conversion có thể thất bại trước các kiểm tra còn lại.

Đây là cách thể hiện **nguyên tắc thiết kế**: một utility nhận nguồn rõ ràng, type rõ ràng và hai handler có trách nhiệm độc lập. Đừng tự động áp dụng utility này cho mọi namespace của một ứng dụng lớn khi chưa xác định quyền sở hữu các khóa cấu hình.

## 15. `NoUnboundElementsBindHandler` và `ignoreUnknownFields=false`

Với bean `@ConfigurationProperties` do Spring Boot quản lý, có thể yêu cầu không bỏ qua unknown fields bằng annotation:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        int threads,
        java.time.Duration timeout,
        boolean enabled
) {}
~~~

Đây là cách khai báo ngắn gọn hơn khi **chỉ cần strict unknown-field checking trong configuration properties bean chuẩn**.

Bảng so sánh:

| Tình huống | Hướng sử dụng |
| --- | --- |
| Đăng ký class qua `@ConfigurationPropertiesScan`, muốn bắt unknown field | `ignoreUnknownFields = false` |
| Tự gọi `Binder.bind(...)` cho một nguồn riêng | `NoUnboundElementsBindHandler` |
| Muốn kiểm tra giá trị với `@Min`, `@NotNull`... | `@Validated` và Jakarta Bean Validation |
| Tự gọi Binder và muốn kiểm tra bằng Spring `Validator` | `ValidationBindHandler` |
| Muốn theo dõi callback binding cho một API riêng | Custom `BindHandler` hoặc handler theo dõi |

`ignoreUnknownFields` của `@ConfigurationProperties` và `NoUnboundElementsBindHandler` có liên hệ về ý tưởng **phát hiện thuộc tính không bind được**. Tuy nhiên, không nên mặc định mọi cấu hình/nguồn/đường đi Binder có chính xác cùng lựa chọn handler nội bộ hoặc cùng định dạng lỗi ở mọi phiên bản.

Một class `@ConfigurationProperties` cũng có `ignoreInvalidFields`, nhưng đó là tùy chọn **khác**:

~~~java
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false,
        ignoreInvalidFields = false
)
~~~

- `ignoreUnknownFields=false`: không chủ động cho phép khóa không bind được dưới phạm vi phù hợp.
- `ignoreInvalidFields=false`: lỗi conversion/binding không được cố tình bỏ qua bởi tùy chọn này.

Với cấu hình quan trọng, giữ strict binding và validation thường giúp phát hiện lỗi sớm.

## 16. `@Validated` trong cơ chế quản lý bean thông thường

Một record cấu hình có thể được khai báo:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        @Min(1) @Max(32) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Đăng ký bean:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(WorkerApplication.class, args);
    }
}
~~~

Khai báo dependency validation (Spring Boot 3.x):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Nếu trong `application.yml` có `threads=0`, Bean Validation có thể từ chối cấu hình bởi `@Min(1)`.

Nếu có `demo.worker.threds=12`, `ignoreUnknownFields=false` có thể từ chối khóa dư.

Nếu `timeout=tomorrow`, conversion thành `Duration` có thể thất bại, không cần chờ Bean Validation.

Điểm cần nhớ: **dùng `@Validated` trong bean `@ConfigurationProperties` và dùng `ValidationBindHandler` trong Binder thủ công là hai đường sử dụng khác nhau**. Chúng dựa trên hạ tầng validation nhưng không được đồng nhất thành cùng một câu lệnh API.

## 17. Giới hạn: `@Validated` không tự đảm bảo mọi thuộc tính được bind

Xét:

~~~yaml
demo:
  worker:
    threads: 4
    timeout: 5s
    enabled: true
    extra-key: ignored
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Nếu không đặt chính sách từ chối unknown fields, các constraint `@Min`/`@NotNull` có thể **đạt** dù `extra-key` bị bỏ qua. Validation kiểm tra **object sau bind**, không tự kiểm kê mọi tên property trong tất cả các nguồn.

Muốn đồng thời bảo vệ:

1. Giá trị đúng về nghiệp vụ.
2. Không có khóa không được liên kết trong phạm vi root.

Có thể dùng:

~~~java
@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
~~~

trong đường bean thông thường, hoặc ghép hai handler khi gọi Binder trực tiếp.

Đừng đánh giá mức độ đầy đủ cấu hình chỉ bằng việc một bean được validate thành công. Một property bị gõ sai tên có thể không tác động gì đến object, trong khi object vẫn thỏa ràng buộc cơ bản nhờ các giá trị khác hoặc default.

## 18. `NoUnboundElementsBindHandler` không phải công cụ phát hiện mọi typo trong hệ thống

Handler phát hiện những property thuộc **root đang bind** nhưng không được xử lý. Ví dụ:

~~~text
Root đang bind: demo.worker

demo.worker.threads           → thuộc phạm vi
demo.worker.threds            → thuộc phạm vi, có thể là unbound
demo.worker-extra.threads     → không cùng root
demo.server.port              → không cùng root
spring.datasource.url         → thuộc namespace khác
~~~

Nếu một typo làm property bị chuyển sang **namespace khác**, handler được gọi cho `demo.worker` không chắc phát hiện được nó.

Ví dụ:

~~~properties
demo.workers.threads=4
~~~

trong khi code bind `demo.worker`. Đây có thể là một cấu hình hoàn toàn nằm **ngoài root**. Nếu không có khóa nào trong `demo.worker`, kết quả có thể là không có object được bind, thay vì một danh sách property unbound.

Vì vậy, với một cấu hình bắt buộc, nên kết hợp:

- Kiểm tra root có dữ liệu hoặc object đã được bind.
- Kiểm tra các field bắt buộc/validation.
- Kiểm tra unbound properties dưới đúng root.
- Tài liệu hóa prefix và cấu trúc cấu hình để hạn chế typo.

Handler không thay cho một schema linter kiểm kê mọi property của toàn hệ thống.

## 19. Giới hạn: nguồn cấu hình phải có khả năng liệt kê property

`NoUnboundElementsBindHandler` cần xác định những cấu hình nào nằm dưới root nhưng không được Binder xử lý. Một số nguồn hỗ trợ **liệt kê tên property**, trong khi những nguồn khác chỉ hỗ trợ lookup theo tên.

Ví dụ `MapPropertySource` có danh sách khóa rõ ràng, phù hợp cho bài test. Nhưng một nguồn tùy chỉnh có thể không cung cấp thông tin enumeration đầy đủ. Khi đó khả năng phát hiện unbound properties có thể bị giới hạn hoặc khác cách bạn hình dung.

Không nên viết một integration test dùng `MapPropertySource` rồi kết luận handler sẽ báo mọi key không được sử dụng từ bất kỳ config backend tùy biến nào.

Đối với cấu hình sản phẩm:

1. Biết property source nào tham gia Binder.
2. Biết nguồn nào có thể enumerate tên.
3. Xác định root prefix cần kiểm tra.
4. Kiểm tra filter nếu dùng.
5. Test với kiểu nguồn thực tế hoặc một test mô phỏng đúng khả năng enumerate.

Nếu yêu cầu pháp lý hoặc vận hành là “không được có property thừa ở bất cứ nguồn nào”, nên có bước validate/lint **schema của nguồn dữ liệu** ở ngoài runtime Binder, thay vì coi một handler là công cụ kiểm kê toàn cục.

## 20. Lọc nguồn khi phát hiện unbound property

`NoUnboundElementsBindHandler` có constructor nhận thêm một hàm filter theo nguồn:

~~~java
new NoUnboundElementsBindHandler(
        parentHandler,
        source -> /* true nếu nguồn cần tham gia kiểm tra */
);
~~~

Trong Spring Boot 3.3, tham số filter có dạng khái niệm:

~~~java
Function<ConfigurationPropertySource, Boolean>
~~~

Tùy implementation, filter cho phép định hướng những nguồn cấu hình nào được xem xét khi phát hiện unbound elements.

Một ví dụ minh họa cú pháp:

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        BindHandler.DEFAULT,
        source -> true
);
~~~

Ví dụ này cho phép tất cả nguồn tham gia theo predicate được truyền, nhưng **không bảo đảm các nguồn không enumerable tự nhiên trở thành enumerable**. Khi áp dụng vào `Environment` lớn, filter `source -> true` có thể không thích hợp vì nhiều namespace dùng chung và nhiều nguồn chứa những property không thuộc trách nhiệm bean hiện tại.

Thực hành:

- Ưu tiên một MapPropertySource hoặc bộ nguồn độc lập cho thư viện cấu hình chuyên biệt.
- Nếu dùng filter, nêu rõ tiêu chí loại nguồn và viết test về danh sách property được xem xét.
- Tránh các filter phụ thuộc vào tên source chưa được chuẩn hóa hoặc chi tiết triển khai không ổn định.
- Đừng đặt `source -> false` rồi nghĩ vẫn đang kiểm tra unknown fields: cách đó có thể làm việc phát hiện unbound mất tác dụng.

## 21. Một handler quan sát property đã bind

Spring Boot có handler phục vụ quan sát các property được bind thành công:

~~~java
org.springframework.boot.context.properties.bind.BoundPropertiesTrackingBindHandler
~~~

Ý tưởng sử dụng:

~~~java
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.BoundPropertiesTrackingBindHandler;

BindHandler tracking = new BoundPropertiesTrackingBindHandler(
        property -> {
            System.out.println("Bound property: " + property.getName());
        }
);
~~~

`BoundPropertiesTrackingBindHandler` nhận một consumer của `ConfigurationProperty`. Nó hữu ích để thu thập **tên** các property đã bind, hỗ trợ chẩn đoán hoặc metric.

Tuy nhiên, nó không tự kiểm tra giá trị có hợp lệ hay không và không tự từ chối các property dư. Có thể cần kết hợp với:

~~~java
new ValidationBindHandler(...)
new NoUnboundElementsBindHandler(...)
~~~

Lưu ý bảo mật: không log tất cả giá trị của `ConfigurationProperty`, vì có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm. Ngay cả **tên** property cũng có thể chứa tenant ID hoặc đường dẫn nội bộ. Việc quan sát cần tuân theo chính sách log của hệ thống.

## 22. Tự viết `BindHandler` để thêm audit

Một custom handler nhỏ có thể kế thừa `AbstractBindHandler` và chỉ quan sát tên:

~~~java
import org.springframework.boot.context.properties.bind.AbstractBindHandler;
import org.springframework.boot.context.properties.bind.BindContext;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;

public final class LoggingBindHandler extends AbstractBindHandler {

    public LoggingBindHandler(BindHandler parent) {
        super(parent);
    }

    @Override
    public Object onSuccess(
            ConfigurationPropertyName name,
            Bindable<?> target,
            BindContext context,
            Object result) {

        System.out.println("Bound name: " + name);

        return super.onSuccess(name, target, context, result);
    }
}
~~~

Cách sử dụng:

~~~java
BindHandler handler = new LoggingBindHandler(
        new NoUnboundElementsBindHandler(
                new ValidationBindHandler(
                        new WorkerSettingsValidator()
                )
        )
);
~~~

Ở đây handler ngoài ghi tên property thành công rồi delegate cho parent. Không cần override `onFailure` nếu không có nhu cầu thay đổi cách xử lý lỗi.

**Điểm quan trọng:** đừng vô tình viết `onFailure` trả một giá trị mặc định tùy tiện cho tất cả exception; điều đó có thể che lỗi chuyển kiểu, lỗi validation hoặc lỗi unknown property và khiến cấu hình sai vẫn đi tiếp.

Trong production, việc log tên property của mọi bind operation có thể gây nhiều log. Nên dùng debug logging có kiểm soát, metrics đếm tổng hoặc audit có giới hạn hơn là in tất cả tên khi khởi động.

## 23. Không nhầm `IgnoreErrorsBindHandler` với validation hoặc strict unknown checking

Spring Boot có các handler với tên thể hiện chính sách xử lý lỗi khác nhau, chẳng hạn:

~~~text
IgnoreErrorsBindHandler
IgnoreTopLevelConverterNotFoundBindHandler
ValidationBindHandler
NoUnboundElementsBindHandler
~~~

Chúng không thay thế cho nhau.

- `IgnoreErrorsBindHandler` có mục tiêu bỏ qua những lỗi binding có thể bỏ qua.
- `IgnoreTopLevelConverterNotFoundBindHandler` có mục tiêu xử lý một tình huống converter ở tầng root.
- `ValidationBindHandler` kiểm tra kết quả theo validator.
- `NoUnboundElementsBindHandler` yêu cầu không còn property dưới root bị bỏ sót.

Việc ghép một handler bỏ qua lỗi với handler nghiêm ngặt có thể tạo semantics khó đoán nếu không xác định thứ tự và điều kiện. Ví dụ conversion error bị bỏ qua có thể khiến một property không tạo được giá trị; liệu nó có còn được coi là bound, hoặc có bị báo dư, còn phụ thuộc cách handler và Binder tương tác.

Với nhu cầu **fail fast** khi cấu hình sai, không nên thêm ignore handler chỉ để giảm số lượng exception.

## 24. Kiểm thử handler với ba trường hợp trọng yếu

Một bộ test tối thiểu nên có:

1. Cấu hình hợp lệ: bind thành công.
2. Cấu hình đúng kiểu nhưng sai điều kiện: validation thất bại.
3. Cấu hình có property dư: strict unbound checking thất bại.

Có thể tạo test JUnit 5/AssertJ cho utility `StrictConfigLoader`:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StrictConfigLoaderTest {

    @Test
    void bindsValidConfiguration() {
        WorkerSettings settings = StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "4",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true"
                )
        );

        assertThat(settings.threads()).isEqualTo(4);
    }

    @Test
    void rejectsBusinessRuleViolation() {
        assertThatThrownBy(() -> StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "0",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true"
                )
        )).isInstanceOf(RuntimeException.class);
    }

    @Test
    void rejectsUnboundProperty() {
        assertThatThrownBy(() -> StrictConfigLoader.load(
                Map.of(
                        "demo.worker.threads", "4",
                        "demo.worker.timeout", "5s",
                        "demo.worker.enabled", "true",
                        "demo.worker.threds", "10"
                )
        )).isInstanceOf(RuntimeException.class);
    }
}
~~~

Các test dùng loại exception rất rộng để minh họa hành vi. Trong dự án thực tế, nên bổ sung assertion **về cause chain và tên property** theo phiên bản Spring Boot đang dùng, để test chứng minh đúng nguyên nhân thay vì chỉ chứng minh bất kỳ RuntimeException nào.

Ngoài ba trường hợp trên, cần test:

- Conversion error (ví dụ `threads=many`).
- Thiếu thuộc tính bắt buộc (ví dụ timeout).
- Nested object không hợp lệ.
- Property thừa trong một nested prefix.
- Nhiều property source có cùng tên nhưng mức ưu tiên khác nhau.
- Nguồn không hỗ trợ enumeration.
- Trường hợp root không có thuộc tính nào.

Không cần chạy tất cả test cho mọi class cấu hình, nhưng nên có ít nhất một bộ test đại diện cho chính sách strict binding nếu nó là một phần hợp đồng triển khai.

## 25. Kiểm thử nested object

Giả sử cấu hình:

~~~yaml
demo:
  gateway:
    endpoint: https://gateway.example.org
    retry:
      max-attempts: 3
      backoff: 2s
~~~

Java:

~~~java
import java.time.Duration;

public record GatewaySettings(
        String endpoint,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {}
}
~~~

Một property thừa:

~~~properties
demo.gateway.retry.max-attempts=3
demo.gateway.retry.backoff=2s
demo.gateway.retry.max-attemtps=10
~~~

Nếu bind root `demo.gateway` với `NoUnboundElementsBindHandler` và nguồn enumerable, khóa typo dưới `retry` có thể được phát hiện. Điều này giúp tránh trường hợp một setting bị bỏ qua trong cấu trúc nhiều cấp.

Nhưng phần **giá trị hợp lệ của nested object** vẫn phải do validator xử lý. Ví dụ `max-attempts=-2` có thể chuyển thành `int` nhưng không hợp lý; `NoUnboundElementsBindHandler` không quyết định điều kiện đó.

Muốn nested validation, có thể:

- Viết Spring `Validator` hỗ trợ `GatewaySettings` và kiểm tra `retry`.
- Dùng Jakarta Bean Validation với `@Valid` và `@Validated` trong pipeline `@ConfigurationProperties`.
- Hoặc đặt validation invariant trong constructor khi quy tắc đơn giản.

Không nên giả định một validator chỉ hỗ trợ `WorkerSettings` sẽ tự kiểm tra `GatewaySettings` và mọi nested type.

## 26. Kiểm thử collection và Map

Các nguồn có cấu trúc phức tạp:

~~~yaml
demo:
  destinations:
    - name: catalog
      timeout: 3s
    - name: inventory
      timeout: 5s
  labels:
    region: asia
    environment: prod
~~~

Java:

~~~java
public record RouteSettings(
        java.util.List<Destination> destinations,
        java.util.Map<String, String> labels
) {
    public record Destination(String name, Duration timeout) {}
}
~~~

Với list và map:

- Tên phẳng của list có thể dùng `destinations[0].name`.
- Map scalar có thể sử dụng `labels.region`.
- Khi Map key chứa dấu chấm hoặc ký hiệu đặc biệt, cần hiểu quy tắc bracket notation của Binder.
- Unknown element ở một list item có thể được phát hiện khi nguồn và handler hỗ trợ việc enumerating tên thuộc tính.
- Validation của từng element cần validator thích hợp hoặc cascade Bean Validation theo mô hình bean.

Ví dụ typo `destinations[1].timeot=5s` không có field tương ứng với `Destination.timeout`. Unbound handler có thể giúp phát hiện nó, còn validator có thể bổ sung yêu cầu rằng timeout của từng item phải khác null và dương.

Đối với collection, tránh tuyên bố rằng Binder luôn ghép list từ các property source. List thường dùng semantics thay thế theo nguồn ưu tiên cao, trong khi map có cách hợp nhất entry khác. Điều này tác động đến tập property mà handler nhìn thấy trong lần bind.

## 27. Thứ tự ưu tiên của property source vẫn quan trọng

Giả sử:

~~~yaml
# application.yml
demo:
  worker:
    threads: 4
~~~

Một biến môi trường có:

~~~bash
DEMO_WORKER_THREADS=0
~~~

Khi Binder lấy cấu hình từ `Environment` của ứng dụng Spring Boot, biến môi trường thường có ưu tiên cao hơn Config Data. Giá trị cuối cho `demo.worker.threads` có thể là 0, dẫn đến vi phạm điều kiện của validator.

`ValidationBindHandler` kiểm tra **kết quả bind thực tế** theo thứ tự nguồn mà Binder sử dụng, không phải chỉ giá trị trong một file.

Với `NoUnboundElementsBindHandler`, cần phân biệt:

- Cùng một property name xuất hiện ở nhiều nguồn: đó thường là chuyện **override** chứ không phải tự động là lỗi property thừa.
- Property name khác nhau nhưng cùng namespace: có thể là khóa dư hoặc typo.
- Alias/canonical name và cách adapter xử lý tên có thể ảnh hưởng quá trình theo dõi binding.

Không nên cấu hình handler để coi mọi property bị nguồn ưu tiên khác ghi đè là “unbound”. Điều người triển khai cần thường là **không có unknown key** trong schema, không phải không có trùng tên giữa các nguồn.

## 28. Lấy Binder từ `Environment` trong ứng dụng

Với Spring Boot 3.3, `Binder` có phương thức lấy Binder từ `Environment`:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class BinderUsage {

    public static Binder fromEnvironment(Environment environment) {
        return Binder.get(environment);
    }
}
~~~

Cách này cho phép Binder nhìn các cấu hình đã được Spring Boot nạp vào `Environment`.

Tuy nhiên:

- Đây là **tập nguồn cấu hình rộng hơn** `MapPropertySource` test riêng.
- Có thể có những key cùng prefix được dùng bởi các thành phần khác.
- Thứ tự ưu tiên và alias phụ thuộc nguồn trong môi trường thực tế.
- Không nên dùng global binder với một strict handler trên một root quá rộng như `"spring"` rồi yêu cầu không còn bất kỳ property unbound nào.
- Các property source riêng có thể không enumerable theo cách giống test map.

Đối với thư viện cấu hình riêng, một `MapPropertySource` độc lập và root hẹp thường dễ kiểm soát hơn. Với bean `@ConfigurationProperties` của ứng dụng, ưu tiên dùng cơ chế Boot chuẩn và các annotation phù hợp trước khi tự triển khai pipeline Binder.

## 29. Phân biệt validation Spring Validator và Jakarta Bean Validation

Có hai cách kiểm tra thường gặp:

**A. Spring `Validator` tự viết**

~~~java
public final class WorkerSettingsValidator
        implements org.springframework.validation.Validator {
    // supports(...) và validate(...) do dự án định nghĩa.
}
~~~

Đưa vào:

~~~java
new ValidationBindHandler(new WorkerSettingsValidator())
~~~

**B. Jakarta Bean Validation trên `@ConfigurationProperties`**

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.worker")
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout
) {}
~~~

Với cách B, cần runtime Bean Validation provider phù hợp, thường qua `spring-boot-starter-validation` trong Spring Boot 3.x.

Nếu muốn tích hợp Jakarta Bean Validation vào **Binder thủ công**, phải cung cấp một Spring `Validator` adapter/phù hợp hoặc một `LocalValidatorFactoryBean` đã được khởi tạo đúng. Không chỉ thêm `@Validated` vào target class rồi mặc định rằng `new Binder(...)` sẽ tự tìm hạ tầng validation của application context và chạy constraint.

Một cách tiếp cận dễ bảo trì:

- Dùng `@Validated` và constraint cho bean `@ConfigurationProperties` chuẩn.
- Dùng `ValidationBindHandler` với Spring `Validator` khi cần kiểm soát một lần `Binder.bind(...)`.
- Không tạo nhiều validator có cùng điều kiện nếu có thể tái sử dụng chúng hợp lý.

## 30. Khi nào nên sử dụng `ConfigurationPropertiesBindHandlerAdvisor`?

Đối với framework extension nâng cao, Spring Boot cung cấp:

~~~java
org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor
~~~

Đây là cơ chế cho phép thêm chức năng vào `BindHandler` mà `ConfigurationPropertiesBindingPostProcessor` sử dụng.

Ví dụ về hình dạng API:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindHandlerAdvisor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingCustomization {

    @Bean
    static ConfigurationPropertiesBindHandlerAdvisor bindingAdvisor() {
        return handler -> handler;
    }
}
~~~

Đây là advisor **no-op**, chỉ minh họa chữ ký và nơi khai báo. Một implementation có thể trả về handler mới bọc handler hiện tại để thêm audit, validation đặc biệt hoặc logic phù hợp.

Vì advisor tác động đến **pipeline binding do Spring Boot quản lý**, nó có thể ảnh hưởng nhiều bean `@ConfigurationProperties`, không chỉ một lần bind trong test. Đó là khác biệt rất lớn so với truyền handler trực tiếp vào `binder.bind(...)`.

Không nên thêm advisor vào application context chỉ để xử lý một thuộc tính riêng nếu `ignoreUnknownFields=false` hoặc `@Validated` đã đủ. Khi thật sự mở rộng pipeline, nên:

1. Giữ nguyên handler parent được cung cấp.
2. Không nuốt lỗi từ handler parent một cách vô tình.
3. Giới hạn tác động theo root/target nếu cần.
4. Có integration test cho các bean cấu hình quan trọng.
5. Kiểm tra thứ tự advisor nếu có nhiều extension.
6. Ghi rõ phiên bản Spring Boot và hợp đồng behavior trong tài liệu kỹ thuật.

## 31. Đọc nguyên nhân lỗi thay vì chỉ nhìn thông báo startup

Các lỗi có thể đến từ những lớp khác nhau:

| Lớp lỗi | Nguyên nhân ví dụ | Dấu hiệu có thể gặp |
| --- | --- | --- |
| Conversion | `threads=many` | Lỗi chuyển `String` sang `int` |
| Bean validation | `threads=0` với điều kiện ≥ 1 | `BindValidationException` hoặc thông báo constraint |
| Unbound element | `threds=12` nhưng class không có field | `UnboundConfigurationPropertiesException` |
| Missing required | `timeout` không có | Validator báo null hoặc thiếu cấu hình theo hợp đồng |
| Bean registration | Class chưa được đăng ký | Không tìm thấy bean `WorkerSettings` |
| Config Data | Tệp import bắt buộc không tồn tại | Lỗi load/import Config Data trước khi Binder chạy |

**Tên exception top-level không luôn là nguyên nhân gốc.** Khi Binder hoặc Spring container đóng gói lỗi, một exception chuyên biệt có thể nằm trong chuỗi cause.

Một quy trình chẩn đoán thực tế:

1. Xác định root prefix và target class.
2. Xác định các property source được Binder sử dụng.
3. Phân biệt “khóa không tồn tại”, “khóa có nhưng sai kiểu” và “khóa không có đích”.
4. Xem exception chain để xác định validation/unbound/conversion.
5. Không in giá trị secret khi log.
6. Bổ sung test cho chính tình huống vừa phát hiện.
7. Sửa nguồn cấu hình hoặc schema thay vì tắt strict mode vô cớ.

Nếu lỗi được tạo bởi handler tự viết, đừng mặc định class exception sẽ giống handler built-in; hãy kiểm tra `onFailure`, `onSuccess` và thứ tự parent delegation.

## 32. Không lạm dụng strict unbound checking trên namespace chia sẻ

Một namespace có thể được nhiều bean hoặc subsystem sử dụng. Ví dụ:

~~~properties
demo.notifications.email.enabled=true
demo.notifications.sms.enabled=false
demo.notifications.retry.max-attempts=3
~~~

Nếu class A chỉ bind `demo.notifications.email` nhưng developer dùng root `demo.notifications` và type A không mô tả `sms` hoặc `retry`, strict unbound handler có thể báo các khóa **hợp lệ đối với subsystem khác** là không được liên kết.

Nguyên nhân không phải các khóa đó sai, mà là **phạm vi root không phù hợp với quyền sở hữu schema**.

Phương án tốt hơn:

- Dùng root hẹp, ví dụ `demo.notifications.email`.
- Nếu cần root chung, tạo một parent properties model thể hiện đầy đủ các nhóm con.
- Chỉ dùng strict handler cho nguồn mà subsystem đó thực sự sở hữu.
- Tách file/namespace cấu hình của các nhóm độc lập.
- Nếu cần filter, nêu rõ tiêu chí nguồn được xét.
- Kiểm thử từng môi trường triển khai thay vì chỉ một file dev đơn giản.

Handler strict là công cụ kiểm tra hợp đồng; hợp đồng chỉ có ý nghĩa khi **ranh giới dữ liệu** được xác định rõ.

## 33. Cách dùng handler trong kiểm thử không cần ApplicationContext

Ví dụ unit test thuần với Binder:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.BindHandler;
import org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StrictBindingTest {

    @Test
    void rejectsUnusedProperty() {
        Map<String, Object> properties = Map.of(
                "demo.worker.threads", "4",
                "demo.worker.timeout", "5s",
                "demo.worker.enabled", "true",
                "demo.worker.threds", "12"
        );

        Binder binder = new Binder(
                ConfigurationPropertySources.from(
                        new MapPropertySource("test", properties)
                )
        );

        BindHandler handler =
                new NoUnboundElementsBindHandler(BindHandler.DEFAULT);

        assertThatThrownBy(() ->
                binder.bind(
                        "demo.worker",
                        Bindable.of(WorkerSettings.class),
                        handler
                ).get()
        ).isInstanceOf(RuntimeException.class);
    }
}
~~~

Ví dụ này không cần khởi tạo Spring application context đầy đủ; chỉ cần các thư viện Spring Boot Binder và dependency test phù hợp.

Trong dự án thật, không nên dừng ở assertion `RuntimeException.class`. Sau khi biết chính xác exception chain trong phiên bản Boot đang dùng, thêm assertion cụ thể về unbound property name để tránh test “thành công” vì một lỗi unrelated.

Ví dụ nếu exception có `UnboundConfigurationPropertiesException` ở cause chain, có thể kiểm tra các `ConfigurationProperty` từ `getUnboundProperties()` theo API thực tế.

## 34. Cách dùng `ApplicationContextRunner` cho `@ConfigurationProperties`

Khi muốn kiểm tra cơ chế Spring Boot quản lý bean, `ApplicationContextRunner` của `spring-boot-test` hữu ích.

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "demo.worker",
        ignoreUnknownFields = false
)
public record WorkerSettings(
        @Min(1) int threads,
        @NotNull Duration timeout,
        boolean enabled
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerSettings.class)
    static class TestConfiguration {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsValidValues() {
        runner.withPropertyValues(
                "demo.worker.threads=4",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true"
        ).run(context -> {
            assertThat(context).hasNotFailed();
        });
    }

    @Test
    void rejectsUnknownField() {
        runner.withPropertyValues(
                "demo.worker.threads=4",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true",
                "demo.worker.threds=12"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsInvalidBusinessValue() {
        runner.withPropertyValues(
                "demo.worker.threads=0",
                "demo.worker.timeout=5s",
                "demo.worker.enabled=true"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

Để validation test thực sự hoạt động, cần có Bean Validation provider đúng version trên test runtime. Nếu context thất bại vì thiếu một bean khác, test `hasFailed()` đơn thuần chưa đủ: hãy bổ sung assertion về nguyên nhân phù hợp.

Đây là **đường dùng auto configuration properties**; không phải tự truyền một `ValidationBindHandler` vào lời gọi `binder.bind(...)`. Cả hai cách phục vụ mục tiêu tương tự nhưng có cách cấu hình và phạm vi khác nhau.

## 35. Trường hợp có cả unbound và invalid: lỗi nào xuất hiện?

Giả sử dữ liệu:

~~~properties
demo.worker.threads=0
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=12
~~~

Có hai vấn đề đồng thời:

1. `threads=0` không thỏa quy tắc ≥ 1.
2. `threds` là property không được bind.

Không nên giả định một lần bind với hai handler sẽ luôn trả về **cả hai lỗi** trong một exception duy nhất. Handler có thể ném exception ở callback trước khi bước kiểm tra còn lại hoàn tất. Thứ tự wrapper, loại bean và đường đi bind có thể quyết định lỗi đầu tiên được thấy.

Để chẩn đoán đầy đủ:

- Chạy test validation riêng cho giá trị.
- Chạy test unknown-field riêng cho schema.
- Sau đó test kết hợp để xác nhận chiến lược fail-fast của ứng dụng.
- Với tool lint ngoài runtime, nếu cần liệt kê nhiều lỗi cùng lúc thì thiết kế cơ chế thu thập lỗi tường minh thay vì dựa vào một lần Binder.bind.

**Fail-fast** và **collect-all-errors** là hai mục tiêu khác nhau. `BindHandler` cho phép mở rộng quy trình bind, nhưng không tự cung cấp một báo cáo toàn diện về mọi lỗi cấu hình trong tất cả các nguồn.

## 36. Khi nào nên chọn cách triển khai nào?

| Bối cảnh | Cách làm phù hợp |
| --- | --- |
| App Spring Boot bình thường với vài bean cấu hình | `@ConfigurationProperties` + `@Validated` + constraints |
| Muốn từ chối typo trong namespace một bean | `ignoreUnknownFields=false` |
| Thư viện cần bind cấu hình từ nguồn riêng | `new Binder(...)` + handler |
| Cần validator chuyên biệt khi bind thủ công | `ValidationBindHandler` với Spring `Validator` |
| Cần phát hiện property bị bỏ sót khi bind thủ công | `NoUnboundElementsBindHandler` |
| Cần cả validation và unknown check trong Binder thủ công | Lồng hai handler, test order/exception |
| Cần log tên property đã bind | Tracking handler hoặc custom `AbstractBindHandler` |
| Cần tùy biến pipeline của tất cả `@ConfigurationProperties` bean | `ConfigurationPropertiesBindHandlerAdvisor` với giới hạn tác động rõ ràng |
| Cần rà toàn bộ các file cấu hình giữa môi trường | Schema lint/CI riêng, không chỉ một runtime BindHandler |

Với phần lớn ứng dụng, **annotation-level validation/strictness** dễ bảo trì hơn việc dựng một pipeline Binding tùy chỉnh. Tự dùng handler thường dành cho thư viện, công cụ cấu hình và các trường hợp cần kiểm soát vòng đời bind ở mức thấp.

## 37. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `threads=0` vẫn bind thành công | Không có validator hoặc chưa bật validation | Dùng `@Validated`/`@Min(1)` hoặc `ValidationBindHandler` |
| Property `threds` bị bỏ qua | Chưa bật strict unknown-field checking | `ignoreUnknownFields=false` hoặc `NoUnboundElementsBindHandler` |
| Có `@Validated` nhưng Binder thủ công không validate | Tự tạo Binder chưa được cấp validator handler | Truyền `ValidationBindHandler` với validator phù hợp |
| `NoUnboundElementsBindHandler` báo key thuộc component khác | Root prefix quá rộng hoặc nguồn dùng chung | Thu hẹp root, tách nguồn/schema |
| Unbound handler không phát hiện khóa ở namespace khác | Kiểm tra chỉ diễn ra trong root đang bind | Kiểm tra namespace và missing-root riêng |
| Test Map phát hiện unknown nhưng nguồn khác không | Source không enumerable hoặc cách adapter khác | Kiểm tra khả năng enumerate và test đúng nguồn |
| `ValidationBindHandler` báo lỗi ở nested type không như mong đợi | Validator không hỗ trợ target/nested type | Chỉnh `supports`/validation cascade và test |
| Có nhiều lỗi nhưng chỉ thấy một | Fail-fast, callback order và exception propagation | Test từng nhóm lỗi, cân nhắc lint riêng nếu cần collect-all |
| Ghi log từ handler làm lộ giá trị nhạy cảm | Log toàn bộ property/result | Chỉ ghi thông tin an toàn, che secret |
| Custom `onFailure` nuốt hết exception | Handler trả default tùy ý | Delegate hoặc rethrow lỗi không được phép bỏ qua |
| `@ConfigurationProperties` không tạo bean | Chưa đăng ký qua scan/enable hoặc nhầm `@Component` | Kiểm tra bean registration |
| Bật `ignoreInvalidFields=true` để chữa typo | Sai loại lỗi; có thể che conversion error | Phân biệt unknown và invalid |
| Gọi `Binder.get(environment)` rồi strict-check root `spring` | Root quá rộng, nhiều owner/schema | Chỉ bind root hẹp và xác định nguồn |
| Kiểm tra thiếu property bằng NoUnbound handler | Không có key dư để phát hiện | Dùng required constraints/default có chủ đích |
| Chỉ assert mọi RuntimeException trong test | Test có thể pass vì lỗi unrelated | Assert nguyên nhân và tên property |
| Giữa hai version Boot exception format đổi | Dựa vào message string không ổn định | Kiểm tra API/cause chain thay vì match text mơ hồ |

## 38. Bài tập tự luyện

### Bài 1 — Phân loại lỗi

Cho:

~~~properties
demo.worker.threads=many
demo.worker.timeout=5s
demo.worker.enabled=true
~~~

Target `threads` có kiểu `int`. Đây là lỗi loại nào?

**Đáp án:** lỗi conversion/binding. `many` không chuyển được thành `int`. Có thể không tạo được object để validator nghiệp vụ kiểm tra.

### Bài 2 — Value hợp lệ về kiểu nhưng sai nghiệp vụ

Cho:

~~~properties
demo.worker.threads=0
demo.worker.timeout=5s
demo.worker.enabled=true
~~~

Validator yêu cầu `threads >= 1`. Handler nào có trách nhiệm?

**Đáp án:** `ValidationBindHandler` với Spring `Validator` phù hợp, hoặc Bean Validation khi đi qua bean `@Validated @ConfigurationProperties` chuẩn.

### Bài 3 — Property thừa

Cho:

~~~properties
demo.worker.threads=4
demo.worker.timeout=5s
demo.worker.enabled=true
demo.worker.threds=7
~~~

Target chỉ có `threads`, `timeout`, `enabled`. Handler nào phù hợp để phát hiện `threds`?

**Đáp án:** `NoUnboundElementsBindHandler` khi nguồn hỗ trợ việc liệt kê và root `demo.worker` được bind phù hợp.

### Bài 4 — Property thiếu

Cho:

~~~properties
demo.worker.threads=4
demo.worker.enabled=true
~~~

Thiếu `timeout`. `NoUnboundElementsBindHandler` có chắc báo lỗi không?

**Đáp án:** không. Handler này tìm các property có mặt nhưng không được bind. Timeout thiếu cần validation hoặc logic required field riêng.

### Bài 5 — Ghép handler

Viết expression tạo handler có cả kiểm tra unbound và validation:

**Đáp án gợi ý:**

~~~java
BindHandler handler = new NoUnboundElementsBindHandler(
        new ValidationBindHandler(
                new WorkerSettingsValidator()
        )
);
~~~

Lưu ý test hành vi khi xuất hiện nhiều lỗi đồng thời.

### Bài 6 — Root của lần bind

Nếu bind root `demo.worker` mà dữ liệu bị gõ thành `demo.workers.threads=4`, strict unbound handler có nhất thiết phát hiện không?

**Đáp án:** không. Property ở namespace khác có thể nằm ngoài root `demo.worker`. Cần kiểm tra root và sự hiện diện của các giá trị bắt buộc.

### Bài 7 — Nguồn không enumerable

Một custom ConfigurationPropertySource chỉ lookup theo key và không hỗ trợ liệt kê. Có thể tuyên bố NoUnbound handler sẽ phát hiện mọi unknown property không?

**Đáp án:** không. Phát hiện unbound phụ thuộc vào nguồn và khả năng enumerating phù hợp.

### Bài 8 — Annotation so với Binder thủ công

Một record có `@Validated` và `@Min(1)`, nhưng code trực tiếp gọi:

~~~java
new Binder(sources).bind(
        "demo.worker",
        Bindable.of(WorkerSettings.class)
);
~~~

Có nên mặc định rằng validation tự chạy?

**Đáp án:** không. Với Binder thủ công, phải cấp handler validator thích hợp hoặc dùng cơ chế pipeline đã tích hợp validation. Chỉ có annotation trên target class không đủ để khẳng định lời gọi này tự kiểm tra constraints.

### Bài 9 — Handler advisor

`ConfigurationPropertiesBindHandlerAdvisor` phù hợp hơn cho trường hợp nào: (A) chỉ một test Bind từ MapPropertySource, hay (B) tùy biến handler mà Spring Boot dùng cho các bean `@ConfigurationProperties`?

**Đáp án:** (B). Với (A), truyền handler trực tiếp vào `Binder.bind(...)` thường rõ và hẹp hơn.

### Bài 10 — Hai lỗi đồng thời

Cấu hình có `threads=0` và `threds=7`. Vì sao không nên yêu cầu một lần Binder.bind luôn trả cả hai trong một danh sách?

**Đáp án:** các handler có thể fail-fast tại callback khác nhau; thứ tự wrapper và quá trình bind ảnh hưởng lỗi được thấy đầu tiên. Nếu cần báo cáo đầy đủ, thiết kế thêm lint/validation thu thập lỗi riêng.

## 39. Checklist áp dụng thực tế

Khi cần dùng handler để bảo vệ cấu hình:

1. Xác định **root prefix** và schema mà thành phần sở hữu.
2. Chọn đường đi: bean `@ConfigurationProperties` chuẩn hay Binder thủ công.
3. Phân loại lỗi muốn phát hiện: conversion, validation, unbound, missing.
4. Với bean chuẩn, ưu tiên `@Validated` và `ignoreUnknownFields=false` nếu đủ.
5. Với Binder thủ công, tạo nguồn `ConfigurationPropertySource` rõ ràng.
6. Chọn `ValidationBindHandler` và/hoặc `NoUnboundElementsBindHandler`.
7. Khi có nhiều handler, xác định quan hệ parent và ghi test thứ tự tương tác.
8. Dùng validator có điều kiện phù hợp với type thực tế.
9. Không tự bỏ qua lỗi trong `onFailure` nếu không có chính sách rõ.
10. Kiểm tra nguồn cấu hình có khả năng enumerate keys để unbound handler hoạt động.
11. Không áp strict policy cho prefix chia sẻ quá rộng.
12. Test cấu hình hợp lệ, sai conversion, sai validation và có unbound property.
13. Test riêng trường hợp không có root hoặc property bắt buộc thiếu.
14. Với nested object/list/map, kiểm tra cả thuộc tính con và ký tự đặc biệt trong key.
15. Tìm nguyên nhân lỗi trong exception chain, không chỉ dựa vào tên exception ngoài cùng.
16. Đảm bảo log và error reporting không làm lộ secret.
17. Kiểm tra sự khác biệt giữa property source của test và production.
18. Gắn trách nhiệm cấu hình vào đúng module/owner để tránh strict checking quá phạm vi.
19. Nếu cần collect-all errors từ nhiều file, bổ sung bước schema lint/CI.
20. Đối chiếu tài liệu API với đúng phiên bản Spring Boot của dự án.

## 40. Ghi nhớ

- **`BindHandler`** cho phép chạy logic trong vòng đời binding thông qua các callback như `onStart`, `onSuccess`, `onFailure` và `onFinish`.
- **`ValidationBindHandler`** áp dụng Spring `Validator` lên kết quả bind để kiểm tra điều kiện nghiệp vụ.
- **`NoUnboundElementsBindHandler`** yêu cầu các property dưới root đang bind được liên kết; nó hữu ích để phát hiện typo hoặc setting thừa.
- **Unbound** khác **missing**. Khóa thừa có mặt nhưng không được dùng; khóa bắt buộc thiếu không phải unbound.
- **Conversion failure** khác **validation failure**. Chuỗi `many` không chuyển thành `int`; số `0` chuyển thành công nhưng có thể vi phạm `@Min(1)`.
- Hai handler có thể được **lồng theo quan hệ parent**; callback order ảnh hưởng lỗi nào xuất hiện trước.
- Với bean `@ConfigurationProperties` chuẩn, thường ưu tiên **`@Validated`** và **`ignoreUnknownFields=false`** trước khi tự quản lý pipeline Binder.
- Binder thủ công không tự lấy Bean Validation provider chỉ vì target class có `@Validated`; phải cấp validator/handler phù hợp.
- Phát hiện unbound phụ thuộc **root prefix, nguồn cấu hình và khả năng liệt kê property**; không phải phép kiểm kê toàn bộ Environment.
- `ConfigurationPropertiesBindHandlerAdvisor` dành cho tùy biến pipeline configuration properties rộng hơn, nên sử dụng có giới hạn và kiểm thử.
- Handler không được vô tình ghi log secret hoặc nuốt lỗi cấu hình quan trọng.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — BindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindHandler.html)
- [Spring Boot 3.3 — ValidationBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html)
- [Spring Boot 3.3 — NoUnboundElementsBindHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/handler/NoUnboundElementsBindHandler.html)
- [Spring Boot 3.3 — ConfigurationPropertiesBindHandlerAdvisor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindHandlerAdvisor.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
