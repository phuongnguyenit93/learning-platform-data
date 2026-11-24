# ObservationDocumentation để mô tả danh mục quan sát và các khóa dữ liệu

Trong một thư viện hoặc ứng dụng có nhiều điểm instrumentation, tên Observation và các khóa dữ liệu dễ bị khai báo rải rác giữa service, convention và handler. Khi một nhóm thay đổi tên tag hoặc thêm thuộc tính, tài liệu có thể lệch khỏi code đang chạy.

Micrometer cung cấp **ObservationDocumentation** để mô tả instrumentation ngay trong mã nguồn. Thông thường ta triển khai interface này bằng một **enum**: mỗi enum constant đại diện cho một loại Observation; các phương thức của enum mô tả tên kỹ thuật, tên dễ đọc, convention mặc định, tiền tố tag, danh sách khóa low/high cardinality và các event có thể phát ra.

Catalog này có hai vai trò: cung cấp metadata có cấu trúc cho người đọc và công cụ sinh tài liệu, đồng thời cung cấp các phương thức tiện ích để tạo hoặc bắt đầu Observation theo đúng quy ước đã khai báo. Nó không tự tạo metrics hoặc spans; các convention và ObservationHandler vẫn chịu trách nhiệm tạo metadata và xử lý vòng đời.

## 1. ObservationDocumentation giải quyết vấn đề gì?

Một instrumentation có thể được gọi ở nhiều nơi. Nếu mỗi nơi tự viết chuỗi tên và tag, các lỗi thường gặp là:

- Cùng một thao tác nhưng mỗi nơi dùng một observation name khác nhau.
- Một tag đổi tên ở convention nhưng test hoặc tài liệu vẫn dùng tên cũ.
- Khóa có giá trị hữu hạn bị xếp nhầm thành high cardinality, hoặc ngược lại.
- Nhiều loại Observation dùng chung tên nhưng có tập tag khác nhau, gây xung đột ở metrics backend.
- Người dùng thư viện không biết Observation nào tồn tại, có tag nào và event nào có thể xuất hiện.

ObservationDocumentation tập trung mô tả các hợp đồng đó trong một nơi. Công cụ Micrometer Docs Generator có thể quét enum triển khai ObservationDocumentation và sinh tài liệu Asciidoctor, giúp tài liệu instrumentation theo sát code.

Một catalog thường gồm:

| Thành phần | Nội dung được mô tả |
|---|---|
| Enum constant | Một loại Observation, ví dụ PROCESS_CHECKOUT hoặc REFUND |
| Observation name | Tên kỹ thuật ổn định dùng cho metrics/tracing |
| Contextual name | Tên dễ đọc cho span hoặc ngữ cảnh quan sát |
| Prefix | Tiền tố bắt buộc của các tag keys trong loại Observation |
| Default convention | Lớp convention cung cấp tên và key-values mặc định |
| Low-cardinality keys | Các khóa có tập giá trị hữu hạn, có thể dùng làm meter tags |
| High-cardinality keys | Các khóa có tập giá trị không giới hạn, thường dành cho tracing |
| Events | Các giá trị Observation.Event mà instrumentation có thể phát |

## 2. Tổ chức catalog bằng enum

ObservationDocumentation thường được triển khai bằng một enum. Mỗi enum constant biểu diễn một loại quan sát có lifecycle riêng.

Ví dụ, một hệ thống thương mại điện tử có thể mô tả hai thao tác:

- PROCESS_CHECKOUT: xử lý một lần checkout.
- REFUND_PAYMENT: hoàn tiền cho một giao dịch.

~~~java
import io.micrometer.observation.docs.ObservationDocumentation;

public enum CommerceObservationDocumentation
        implements ObservationDocumentation {

    /**
     * Observation bao quanh quá trình xử lý checkout của một đơn hàng.
     */
    PROCESS_CHECKOUT {
        // Metadata được khai báo ở các phần sau.
    },

    /**
     * Observation bao quanh quá trình hoàn tiền cho một giao dịch.
     */
    REFUND_PAYMENT {
        // Metadata riêng cho thao tác hoàn tiền.
    }
}
~~~

Mỗi enum constant có thể cung cấp bộ metadata khác nhau. Điều này hữu ích khi hai thao tác có tập low-cardinality tags hoặc high-cardinality tags khác nhau. Hãy tách chúng thành các enum constant riêng nếu chúng là hai loại thao tác có ý nghĩa khác nhau, kể cả khi cùng thuộc một service.

Không tạo một enum constant cho mỗi request hoặc mỗi giá trị tag. Catalog mô tả loại instrumentation ổn định, còn giá trị cụ thể được đưa vào context khi Observation chạy.

## 3. Các phương thức quan trọng của ObservationDocumentation

Các phương thức của interface mô tả metadata và cung cấp factory cho Observation:

| Phương thức | Vai trò |
|---|---|
| getName() | Tên kỹ thuật mặc định, ví dụ tên metric |
| getContextualName() | Tên dễ đọc hơn, thường dùng làm span name |
| getPrefix() | Tiền tố bắt buộc phải có trong các tag keys của loại Observation |
| getDefaultConvention() | Lớp convention mặc định cung cấp tên và key-values |
| getLowCardinalityKeyNames() | Danh sách KeyName có cardinality thấp |
| getHighCardinalityKeyNames() | Danh sách KeyName có cardinality cao |
| getEvents() | Danh sách Observation.Event values mà Observation có thể phát |
| observation(...) | Tạo Observation chưa bắt đầu |
| start(...) | Tạo và bắt đầu Observation |

Các danh sách khóa và event có thể để rỗng nếu loại Observation không cần chúng. Interface cung cấp các giá trị rỗng dùng chung như EMPTY và EMPTY_EVENT_NAMES để triển khai mặc định.

### Technical name và contextual name

Technical name là tên ổn định để backend nhận diện loại Observation. Contextual name là tên dễ đọc hơn trong một ngữ cảnh cụ thể.

Ví dụ:

- Technical name: commerce.checkout
- Contextual name: checkout order

Một trong hai nơi có thể định nghĩa tên: enum ObservationDocumentation hoặc default ObservationConvention. Nếu convention mặc định đã cung cấp getName() và getContextualName(), không ghi đè cùng các giá trị đó ở enum. Hãy chọn một nguồn làm chuẩn để tránh hai cấu hình mâu thuẫn.

### Prefix

getPrefix() khai báo tiền tố bắt buộc cho tag keys của loại Observation. Ví dụ prefix commerce.checkout yêu cầu các khóa liên quan dùng dạng commerce.checkout.payment.method hoặc commerce.checkout.channel.

Prefix là metadata mô tả quy ước. Nó không tự động nối chuỗi vào tag key ở runtime. Convention vẫn phải trả về KeyValue với key đúng tiền tố.

## 4. Khai báo KeyName cho low và high cardinality

KeyName nằm trong package io.micrometer.common.docs. Mỗi key nên là một enum constant triển khai KeyName, thay vì khai báo chuỗi tùy ý ở nhiều nơi. Với Micrometer Docs Generator, các enum KeyName cần được khai báo lồng bên trong enum triển khai ObservationDocumentation; getLowCardinalityKeyNames() và getHighCardinalityKeyNames() trả về values() của các enum lồng đó.

KeyName cung cấp các phương thức hữu ích:

- asString(): tên thực tế của key.
- isRequired(): cho biết key có bắt buộc phải xuất hiện trong instrumentation hay không.
- withValue(value): tạo KeyValue với tên key đã định nghĩa.
- withValue(value, validator): tạo KeyValue và kiểm tra giá trị theo validator.

Ví dụ phần khai báo nested enum bên trong CheckoutObservationDocumentation:

~~~java
import io.micrometer.common.docs.KeyName;

enum LowCardinalityKeyNames implements KeyName {

    /**
     * Phương thức thanh toán: card, bank hoặc wallet.
     */
    PAYMENT_METHOD {
        @Override
        public String asString() {
            return "commerce.checkout.payment.method";
        }

        @Override
        public boolean isRequired() {
            return true;
        }
    },

    /**
     * Kênh bắt đầu checkout: web, mobile hoặc store.
     */
    CHANNEL {
        @Override
        public String asString() {
            return "commerce.checkout.channel";
        }
    }
}
~~~

Các giá trị payment method và channel có tập giá trị được kiểm soát, nên phù hợp với low cardinality. Với DefaultMeterObservationHandler, low-cardinality key-values được chuyển thành meter tags.

Ví dụ khóa high cardinality:

~~~java
enum HighCardinalityKeyNames implements KeyName {

    /**
     * Mã đơn hàng đang được checkout.
     */
    ORDER_ID {
        @Override
        public String asString() {
            return "commerce.checkout.order.id";
        }
    }
}
~~~

Order ID thay đổi theo từng đơn hàng nên có thể tạo rất nhiều giá trị. Nó có thể hữu ích làm span attribute để tra cứu một giao dịch cụ thể; không nên đưa nó thành meter tag. High-cardinality key-value không tự động trở thành log field. Không đưa token, thông tin thanh toán hoặc dữ liệu cá nhân vào trace chỉ vì chúng được phân loại high cardinality.

## 5. Định nghĩa event names

Một Observation có thể phát event để biểu thị một mốc đáng chú ý trong lifecycle, chẳng hạn retry, cache miss hoặc fallback. Khác với tag keys, getEvents() nhận các giá trị Observation.Event[]; vì vậy enum event triển khai Observation.Event và cung cấp getName():

~~~java
import io.micrometer.observation.Observation;

enum Events implements Observation.Event {

    /**
     * Checkout phải thử lại một bước xử lý.
     */
    RETRY {
        @Override
        public String getName() {
            return "commerce.checkout.retry";
        }
    },

    /**
     * Checkout sử dụng phương án thanh toán dự phòng.
     */
    PAYMENT_FALLBACK {
        @Override
        public String getName() {
            return "commerce.checkout.payment.fallback";
        }
    }
}
~~~

Enum Events cũng được khai báo nested trong CheckoutObservationDocumentation để catalog và event names nằm cùng một nơi. Event name nên ổn định và có cardinality thấp. Nếu event cần dữ liệu biến thiên, hãy đưa phần đó vào contextual name hoặc event metadata theo API của phiên bản Micrometer đang dùng thay vì tạo một event name mới cho từng giá trị.

Khi phát event, dùng cùng tên đã khai báo:

~~~java
observation.event(
    CheckoutObservationDocumentation.Events.RETRY
);
~~~

Catalog ghi lại các event name hợp lệ, còn lời gọi event() mới thực sự phát tín hiệu đến ObservationHandler.

## 6. Kết hợp catalog và default convention

Convention chuyển context thành technical name, contextual name và key-values. ObservationDocumentation có thể trỏ đến lớp convention mặc định bằng getDefaultConvention().

Context ví dụ:

~~~java
import io.micrometer.observation.Observation;

public final class CheckoutContext extends Observation.Context {

    private final String paymentMethod;
    private final String channel;
    private final String orderId;

    public CheckoutContext(
            String paymentMethod,
            String channel,
            String orderId) {
        this.paymentMethod = paymentMethod;
        this.channel = channel;
        this.orderId = orderId;
    }

    public String paymentMethod() {
        return paymentMethod;
    }

    public String channel() {
        return channel;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

Convention mặc định:

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public final class DefaultCheckoutObservationConvention
        implements ObservationConvention<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public String getName() {
        return "commerce.checkout";
    }

    @Override
    public String getContextualName(CheckoutContext context) {
        return "checkout order";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
        return KeyValues.of(
            CheckoutObservationDocumentation.LowCardinalityKeyNames.PAYMENT_METHOD
                .withValue(context.paymentMethod()),
            CheckoutObservationDocumentation.LowCardinalityKeyNames.CHANNEL
                .withValue(context.channel())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(CheckoutContext context) {
        return KeyValues.of(
            CheckoutObservationDocumentation.HighCardinalityKeyNames.ORDER_ID
                .withValue(context.orderId())
        );
    }
}
~~~

Convention dùng KeyName.withValue() thay vì lặp lại các chuỗi key. Nhờ vậy, tên key trong catalog và tên key được phát ra có cùng nguồn khai báo.

Enum ObservationDocumentation hoàn chỉnh:

~~~java
import io.micrometer.common.docs.KeyName;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.docs.ObservationDocumentation;

public enum CheckoutObservationDocumentation
        implements ObservationDocumentation {

    /**
     * Observation bao quanh một lần xử lý checkout.
     */
    PROCESS_CHECKOUT {
        @Override
        public Class<? extends ObservationConvention<? extends Observation.Context>>
                getDefaultConvention() {
            return DefaultCheckoutObservationConvention.class;
        }

        @Override
        public String getPrefix() {
            return "commerce.checkout";
        }

        @Override
        public KeyName[] getLowCardinalityKeyNames() {
            return LowCardinalityKeyNames.values();
        }

        @Override
        public KeyName[] getHighCardinalityKeyNames() {
            return HighCardinalityKeyNames.values();
        }

        @Override
        public Observation.Event[] getEvents() {
            return Events.values();
        }
    };

    enum LowCardinalityKeyNames implements KeyName {
        /** Phương thức thanh toán: card, bank hoặc wallet. */
        PAYMENT_METHOD {
            @Override
            public String asString() {
                return "commerce.checkout.payment.method";
            }

            @Override
            public boolean isRequired() {
                return true;
            }
        },
        /** Kênh bắt đầu checkout: web, mobile hoặc store. */
        CHANNEL {
            @Override
            public String asString() {
                return "commerce.checkout.channel";
            }
        }
    }

    enum HighCardinalityKeyNames implements KeyName {
        /** Mã đơn hàng đang được checkout. */
        ORDER_ID {
            @Override
            public String asString() {
                return "commerce.checkout.order.id";
            }
        }
    }

    enum Events implements Observation.Event {
        /** Checkout phải thử lại một bước xử lý. */
        RETRY {
            @Override
            public String getName() {
                return "commerce.checkout.retry";
            }
        },
        /** Checkout sử dụng phương án thanh toán dự phòng. */
        PAYMENT_FALLBACK {
            @Override
            public String getName() {
                return "commerce.checkout.payment.fallback";
            }
        }
    }
}
~~~

Ở đây technical name và contextual name được cung cấp bởi DefaultCheckoutObservationConvention. Enum chỉ mô tả prefix, danh sách key và event. Cách tổ chức này giữ phần metadata catalog gọn và tránh khai báo tên hai lần.

## 7. Tạo Observation từ enum documentation

ObservationDocumentation cung cấp factory để tạo Observation bằng default convention đã khai báo. Context được truyền dưới dạng supplier:

~~~java
import io.micrometer.observation.ObservationRegistry;

public final class CheckoutService {

    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void checkout(
            String paymentMethod,
            String channel,
            String orderId) {

        CheckoutObservationDocumentation.PROCESS_CHECKOUT
            .observation(
                observationRegistry,
                () -> new CheckoutContext(
                    paymentMethod,
                    channel,
                    orderId
                )
            )
            .observe(this::performCheckout);
    }

    private void performCheckout() {
        // Xác thực đơn hàng, xử lý thanh toán và cập nhật trạng thái.
    }
}
~~~

Supplier giúp trì hoãn việc tạo context đến khi Micrometer xác định Observation có được bật hay không. Nếu registry là no-op hoặc ObservationPredicate loại bỏ Observation, Micrometer có thể bỏ qua việc tạo context.

Có thể gọi start() nếu muốn tự quản lý lifecycle:

~~~java
import io.micrometer.observation.Observation;

Observation observation =
    CheckoutObservationDocumentation.PROCESS_CHECKOUT.start(
        observationRegistry,
        () -> new CheckoutContext("card", "web", "order-42")
    );

try (Observation.Scope scope = observation.openScope()) {
    performCheckout();
}
catch (RuntimeException error) {
    observation.error(error);
    throw error;
}
finally {
    observation.stop();
}
~~~

Dùng observation() khi muốn gọi observe() để framework tự start, mở scope, ghi nhận lỗi và stop. Dùng start() khi cần điều khiển lifecycle thủ công; khi đó phải bảo đảm mọi đường thoát đều stop Observation.

## 8. Ghi đè convention cho một instrumentation call

Ứng dụng sử dụng thư viện có thể muốn thay đổi cách đặt tên hoặc bổ sung key-value mà không sửa convention mặc định của thư viện.

Có thể truyền custom convention cùng default convention:

~~~java
Observation observation =
    CheckoutObservationDocumentation.PROCESS_CHECKOUT.observation(
        customCheckoutConvention,
        new DefaultCheckoutObservationConvention(),
        () -> new CheckoutContext("card", "web", "order-42"),
        observationRegistry
    );

observation.observe(this::performCheckout);
~~~

Thứ tự chọn convention của Micrometer:

1. Custom convention được truyền trực tiếp khi tạo Observation.
2. Nếu không có custom convention, GlobalObservationConvention phù hợp đã đăng ký trong ObservationRegistry được chọn.
3. Nếu không có global convention phù hợp, default convention được dùng.

ObservationDocumentation giữ vai trò cung cấp default convention và danh mục key names. Nó không ngăn người dùng thay đổi convention; việc cho phép tùy chỉnh là một phần của thiết kế Observation.

Nếu custom convention thay đổi tập key được phát ra, hãy cập nhật catalog hoặc tài liệu tùy chỉnh tương ứng. Nếu không, tài liệu sinh ra có thể không phản ánh metadata thực tế.

## 9. Phân biệt danh sách KeyName và KeyValue thực tế

Một điểm cần nhớ: getLowCardinalityKeyNames() và getHighCardinalityKeyNames() chỉ mô tả những khóa được phép hoặc dự kiến cho loại Observation. Chúng không tự động thêm các khóa đó vào context.

Convention vẫn phải trả về KeyValues qua getLowCardinalityKeyValues() và getHighCardinalityKeyValues(), hoặc instrumentation phải thêm chúng trực tiếp vào Observation.

| Catalog | Runtime |
|---|---|
| KeyName.asString() | KeyValue chứa key và value |
| getLowCardinalityKeyNames() | getLowCardinalityKeyValues(context) |
| getHighCardinalityKeyNames() | getHighCardinalityKeyValues(context) |
| getEvents(): Observation.Event[] | observation.event(...) |
| getDefaultConvention() | Convention thực tế tạo tên và key-values |

Do đó, khai báo ORDER_ID trong high-cardinality key names không tự tạo order ID. Instrumentation cần lấy order ID từ context và convention phải thêm nó vào KeyValues.

Với DefaultMeterObservationHandler, chỉ low-cardinality key-values được dùng làm meter tags. High-cardinality key-values không được đưa vào meter để tránh cardinality explosion. Các handler tracing có thể dùng chúng trong span attributes theo cấu hình tương ứng.

## 10. Quy tắc thiết kế tên và prefix

Một catalog có giá trị khi tên được ổn định và dễ tìm kiếm.

- Chọn technical name theo operation, ví dụ commerce.checkout.
- Contextual name nên mô tả hành động, ví dụ checkout order.
- Chọn một prefix nhất quán cho nhóm tag keys.
- Dùng cùng một quy ước phân cấp cho low và high cardinality keys.
- Tránh viết tắt không rõ nghĩa và tránh dùng tên key phụ thuộc vào tên biến Java.
- Không dùng giá trị runtime để tạo technical name hoặc event name.
- Không tái sử dụng một technical name cho các loại Observation có tập key khác nhau.

Ví dụ hai thao tác PROCESS_CHECKOUT và REFUND_PAYMENT nên có technical name riêng, prefix riêng và danh sách key riêng. Điều này giúp metrics backend giữ schema tag ổn định.

Prefix không tự chuẩn hóa tên key. Nếu prefix là commerce.checkout, convention phải phát key bắt đầu bằng commerce.checkout theo đúng quy ước đã mô tả.

## 11. Sử dụng isRequired để kiểm tra instrumentation

KeyName.isRequired() cho phép đánh dấu một key phải có trong instrumentation. Giá trị mặc định là không bắt buộc; hãy đánh dấu true cho các key mà mọi lần thực thi của loại Observation đó cần cung cấp.

Ví dụ, payment.method là bắt buộc, còn channel có thể không có trong một số luồng đặc biệt.

Có thể kiểm tra các key bắt buộc trong test:

~~~java
@Test
void requiredCheckoutKeysArePresent() {
    CheckoutContext context =
        new CheckoutContext("card", "web", "order-42");

    DefaultCheckoutObservationConvention convention =
        new DefaultCheckoutObservationConvention();

    Set<String> emittedKeys = convention
        .getLowCardinalityKeyValues(context)
        .stream()
        .map(KeyValue::getKey)
        .collect(Collectors.toSet());

    for (KeyName keyName :
            CheckoutObservationDocumentation.PROCESS_CHECKOUT
                .getLowCardinalityKeyNames()) {
        if (keyName.isRequired()) {
            assertTrue(emittedKeys.contains(keyName.asString()));
        }
    }
}
~~~

Cách kiểm tra này giúp phát hiện khi convention quên thêm một key được đánh dấu bắt buộc. Có thể làm tương tự cho high-cardinality keys nếu instrumentation yêu cầu.

Không đánh dấu mọi key là required theo thói quen. Nếu một trường có thể không tồn tại trong một luồng nghiệp vụ hợp lệ, hãy để nó optional và mô tả rõ điều kiện xuất hiện.

## 12. Kiểm thử catalog và convention

Ngoài kiểm tra required keys, nên xác nhận danh sách key trong catalog khớp với danh sách key convention phát ra.

~~~java
@Test
void documentedLowCardinalityKeysMatchConvention() {
    CheckoutContext context =
        new CheckoutContext("card", "web", "order-42");

    Set<String> documented = Arrays.stream(
            CheckoutObservationDocumentation.PROCESS_CHECKOUT
                .getLowCardinalityKeyNames()
        )
        .map(KeyName::asString)
        .collect(Collectors.toSet());

    Set<String> emitted = new DefaultCheckoutObservationConvention()
        .getLowCardinalityKeyValues(context)
        .stream()
        .map(KeyValue::getKey)
        .collect(Collectors.toSet());

    assertEquals(documented, emitted);
}
~~~

Nếu convention có thể phát thêm key tùy chọn, thay vì yêu cầu hai tập bằng nhau, hãy kiểm tra tập key phát ra là tập con của catalog và mọi required key đều có mặt.

Một test với SimpleMeterRegistry có thể xác nhận Observation thực sự tạo Timer với các tag low-cardinality:

~~~java
@Test
void documentationCreatesExpectedTimerAndTags() {
    SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
    ObservationRegistry observationRegistry = ObservationRegistry.create();

    observationRegistry.observationConfig()
        .observationHandler(
            DefaultMeterObservationHandler.builder(meterRegistry).build()
        );

    CheckoutObservationDocumentation.PROCESS_CHECKOUT
        .observation(
            observationRegistry,
            () -> new CheckoutContext("card", "web", "order-42")
        )
        .observe(() -> { });

    assertEquals(
        1,
        meterRegistry.get("commerce.checkout")
            .tag("commerce.checkout.payment.method", "card")
            .tag("commerce.checkout.channel", "web")
            .timer()
            .count()
    );
}
~~~

Test cần đăng ký DefaultMeterObservationHandler; chỉ khai báo ObservationDocumentation không tự tạo meter. Nếu dùng convention khác hoặc registry exporter khác, tên metric và định dạng tag có thể phụ thuộc convention và NamingConvention tương ứng.

## 13. Sinh tài liệu Asciidoctor bằng Micrometer Docs Generator

Micrometer Docs Generator quét source code có triển khai ObservationDocumentation, SpanDocumentation hoặc MeterDocumentation và tạo các file Asciidoctor. Khi instrumentation dùng chính enum đó để tạo Observation, tài liệu được sinh từ cùng metadata mà runtime sử dụng.

ObservationDocumentation thuộc module micrometer-observation, KeyName thuộc micrometer-commons. Micrometer Docs Generator là dependency phục vụ build và sinh tài liệu; không cần đưa nó vào runtime classpath của ứng dụng.

Một cấu hình Gradle Groovy tối giản:

~~~groovy
ext {
    micrometerDocsGeneratorVersion = "1.0.2"
}

configurations {
    micrometerDocsGenerator
}

dependencies {
    micrometerDocsGenerator(
        "io.micrometer:micrometer-docs-generator:$micrometerDocsGeneratorVersion"
    )
}

tasks.register("generateObservabilityDocs", JavaExec) {
    mainClass = "io.micrometer.docs.DocsGeneratorCommand"
    classpath = configurations.micrometerDocsGenerator

    args(
        project.rootDir.absolutePath,
        ".*",
        layout.buildDirectory.dir("generated-observability-docs")
            .get().asFile.absolutePath,
        "--conventions"
    )
}
~~~

Các đối số chính:

| Đối số | Ý nghĩa |
|---|---|
| Input path | Thư mục source cần quét |
| Inclusion pattern | Regex chọn file source |
| Output path | Thư mục lưu tài liệu được sinh |
| --conventions | Sinh tài liệu Observation conventions |

Docs Generator cũng có tùy chọn sinh tài liệu metrics và spans bằng --metrics và --spans. Tùy chọn output cho phép chỉ định tên file đích; mặc định tài liệu convention được ghi vào _conventions.adoc.

Tài liệu sinh ra có thể liệt kê từng Observation, mô tả thao tác, tên metric/span, convention, low-cardinality keys và high-cardinality keys. Javadoc trên enum constant và KeyName constants giúp tài liệu có mô tả dễ hiểu thay vì chỉ có tên kỹ thuật.

Hãy đồng bộ phiên bản Docs Generator với dòng Micrometer đang sử dụng theo tài liệu phát hành. Không dùng một phiên bản snapshot trong pipeline release nếu dự án chưa chủ động chấp nhận snapshot dependency.

## 14. Tổ chức mã nguồn để tài liệu không lệch runtime

Một cấu trúc package có thể tách catalog, context và convention:

~~~text
commerce/
  observation/
    CheckoutContext.java
    CheckoutObservationDocumentation.java
    DefaultCheckoutObservationConvention.java
    CustomCheckoutObservationConvention.java
~~~

Các enum KeyName và event được giữ nested bên trong CheckoutObservationDocumentation để Docs Generator nhận diện đúng catalog. Context và convention vẫn có thể đặt ở file riêng để giữ mã instrumentation dễ đọc.

Các nguyên tắc cần giữ:

- Enum documentation và convention phải được sửa cùng một thay đổi khi schema thay đổi.
- Tên kỹ thuật và tag key phải ổn định giữa các phiên bản nếu backend dashboard phụ thuộc vào chúng.
- Javadoc trên enum constant nên mô tả khi nào Observation được tạo.
- Javadoc trên KeyName constant nên mô tả ý nghĩa, nguồn và giới hạn giá trị.
- Test phải kiểm tra key bắt buộc và tập key thực tế.
- Build tài liệu nên chạy trong CI để phát hiện source không thể quét hoặc tài liệu không sinh được.

Không tạo catalog chỉ để sinh tài liệu nếu instrumentation thực tế vẫn dùng chuỗi tùy ý ở nơi khác. Hãy gọi factory trên enum và dùng KeyName trong convention để giữ code và catalog cùng nguồn khai báo.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng một enum constant cho nhiều loại Observation khác schema | Tên và tập tag có thể không nhất quán | Tách mỗi loại thao tác thành enum constant riêng |
| Nghĩ KeyName tự thêm tag vào Observation | Catalog có key nhưng runtime không phát key | Dùng KeyName.withValue() trong convention |
| Khai báo low/high key sai nhóm | Cardinality và chi phí backend tăng | Đánh giá tập giá trị trước khi phân loại |
| Định nghĩa tên ở cả enum và default convention | Technical/contextual name có thể mâu thuẫn | Chọn một nơi làm nguồn chuẩn |
| Không khai báo prefix hoặc tag keys không theo prefix | Tài liệu và schema tag khó thống nhất | Đặt prefix và dùng nhất quán cho mọi key |
| Dùng event name có giá trị động | Event cardinality tăng không kiểm soát | Dùng event name cố định và đặt dữ liệu biến thiên vào metadata phù hợp |
| Không viết Javadoc cho enum/key constants | Tài liệu sinh ra thiếu mô tả hữu ích | Viết mô tả ngay cạnh constant |
| Nghĩ ObservationDocumentation tự tạo metrics | Không có meter nếu thiếu handler | Đăng ký handler phù hợp, ví dụ DefaultMeterObservationHandler |
| Chỉ kiểm tra catalog mà không kiểm tra convention | Key khai báo và key thực tế có thể lệch | Test tập key được convention phát ra |
| Không chạy Docs Generator trong CI | Tài liệu có thể hỏng hoặc lỗi thời | Thêm task sinh tài liệu vào pipeline |

## 16. Checklist triển khai

- [ ] Mỗi loại Observation có một enum constant riêng.
- [ ] Enum triển khai ObservationDocumentation.
- [ ] Technical name và contextual name có một nguồn định nghĩa rõ ràng.
- [ ] Prefix tag được khai báo và áp dụng nhất quán.
- [ ] Low-cardinality và high-cardinality keys được phân loại đúng.
- [ ] Key names được khai báo bằng enum triển khai KeyName.
- [ ] Các key bắt buộc được đánh dấu bằng isRequired().
- [ ] Event values được khai báo bằng Observation.Event nếu instrumentation phát event.
- [ ] Default convention được khai báo qua getDefaultConvention().
- [ ] Instrumentation tạo Observation qua enum documentation.
- [ ] Convention sử dụng KeyName.withValue() thay cho chuỗi lặp lại.
- [ ] Handler tạo metrics hoặc tracing đã được đăng ký.
- [ ] Test kiểm tra required keys và catalog/runtime consistency.
- [ ] Docs Generator được cấu hình để sinh Asciidoctor docs.
- [ ] CI xác minh tài liệu được sinh thành công.

ObservationDocumentation biến metadata của instrumentation thành một catalog có cấu trúc: enum constant mô tả từng loại quan sát, KeyName mô tả các tag và event, còn convention cung cấp giá trị thực tế từ context. Dùng factory của enum để tạo Observation, kiểm tra catalog với key-values được phát ra và sinh tài liệu từ source bằng Micrometer Docs Generator. Khi các phần này được duy trì cùng nhau, tên, tag schema và tài liệu của instrumentation sẽ nhất quán hơn qua các lần thay đổi.

## Tài liệu tham khảo

- [Micrometer Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Docs Generator](https://docs.micrometer.io/micrometer-docs-generator/reference/)
- [ObservationDocumentation API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/docs/ObservationDocumentation.html)
- [KeyName API](https://javadoc.io/doc/io.micrometer/micrometer-commons/latest/io/micrometer/common/docs/KeyName.html)
- [ObservationConvention API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationConvention.html)

