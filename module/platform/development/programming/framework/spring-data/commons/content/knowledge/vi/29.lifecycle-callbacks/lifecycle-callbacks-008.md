# Phân biệt EntityCallback với lifecycle ApplicationEvent

## 1. Hai cơ chế cùng xuất hiện trong vòng đời nhưng có hợp đồng khác nhau

Trong chương **Vòng đời và callback** của module **SPRING_DATA_COMMONS**, một entity có thể đi qua cả callback và sự kiện lifecycle của store.

Chẳng hạn, trước khi lưu một sản phẩm, ứng dụng muốn:

- Chuẩn hóa mã SKU.
- Quan sát rằng sản phẩm đang đi qua bước chuyển đổi.
- Phát thông báo sau khi giao dịch nghiệp vụ đã thành công.

Ba nhu cầu này không nên được gộp thành một lời gọi “chạy trước hoặc sau save”.

`EntityCallback` phục vụ một điểm can thiệp có hợp đồng nhận lại entity hoặc publisher chứa entity. Lifecycle `ApplicationEvent` thông báo rằng một bước của store đã diễn ra hoặc sắp diễn ra, thông qua cơ chế sự kiện của Spring.

Nếu cần thay entity bằng một bản sao immutable rồi để pipeline tiếp tục với bản sao đó, callback là cơ chế phù hợp khi store hỗ trợ điểm can thiệp tương ứng.

Nếu cần quan sát một lifecycle event, listener là một lựa chọn. Tuy nhiên, thời điểm listener hoàn tất, cách lỗi được truyền và quan hệ với transaction phụ thuộc cấu hình sự kiện.

“Sau save” cũng chưa đủ để kết luận “sau commit”. Đây là một ranh giới riêng cần được thiết kế rõ.

## 2. Bảng đối chiếu trực tiếp

| Tiêu chí | Entity callback | Lifecycle ApplicationEvent |
| --- | --- | --- |
| Thành phần cung cấp hợp đồng | Commons cung cấp marker và dispatcher; store định nghĩa callback cụ thể | Store định nghĩa sự kiện; Spring cung cấp cơ chế publication và listener |
| Đường nhận kết quả | Trả entity hoặc Publisher entity theo interface | Listener thường xử lý thông báo; không có hợp đồng chung thay entity trong pipeline |
| Entity immutable | Có thể trả một entity mới cho bước kế tiếp | Không thể mặc định giá trị trả về của listener thay source của thao tác lưu |
| Entity mutable | Có thể sửa rồi trả lại nếu hợp đồng cho phép | Listener đồng bộ có thể nhìn và sửa object chung; điều đó không tạo một hợp đồng thay entity tương đương callback |
| Thực thi đồng bộ | Dispatcher đồng bộ trả kết quả cho caller | Multicaster mặc định thường gọi listener đồng bộ trong luồng publication |
| Thực thi reactive | Có dispatcher và callback interface reactive tương ứng | ApplicationEvent không tự trở thành một Publisher nằm trong pipeline |
| Thực thi bất đồng bộ | Không tự tách một tác vụ khỏi chuỗi callback | Có thể dùng executor hoặc cơ chế listener bất đồng bộ |
| Thứ tự | Theo cơ chế order trong phạm vi dispatch và giai đoạn | Theo cơ chế listener, multicaster và khả năng bất đồng bộ |
| Quan hệ với commit | Không tự bảo đảm transaction đã commit | Lifecycle event cũng không tự bảo đảm đã commit |
| Phạm vi store | Chỉ các điểm callback được module tích hợp | Chỉ các sự kiện và đường publication mà module thực sự phát |

`EntityCallback<T>` là marker interface, không chứa một phương thức `onSave` chung cho mọi store.

Phương thức cụ thể nằm ở interface như before-convert hoặc before-save của module. Cách thức này cho phép store cung cấp các đối số khác nhau mà không áp đặt một lifecycle giống nhau cho mọi database.

## 3. Đọc đúng thứ tự: phát event trước không luôn có nghĩa listener xong trước

Ở những điểm tích hợp tương ứng của Spring Data MongoDB, lifecycle event có thể được phát trước khi callback cùng giai đoạn được gọi.

Ví dụ định hướng cho before-convert:

~~~mermaid
flowchart TD
    A["Entity đầu vào"] --> B["Phát BeforeConvertEvent"]
    B --> C["Gọi BeforeConvertCallback"]
    C --> D["Nhận entity trả về"]
    D --> E["Chuyển entity thành Document"]
    E --> F["Các bước lưu tiếp theo"]
~~~

Sơ đồ mô tả thứ tự ở đường tích hợp này, không phải một pipeline bắt buộc cho mọi store.

Đặc biệt, mũi tên từ publication đến callback không tự bảo đảm mọi listener đã hoàn tất:

- Với listener đồng bộ, phần xử lý listener chạy trong đường publication.
- Với listener được chuyển sang executor, publication có thể chỉ bàn giao công việc.
- Callback có thể bắt đầu trong khi một listener bất đồng bộ còn đang xử lý.

Do đó, không dùng một listener bất đồng bộ để chuẩn hóa field rồi kỳ vọng before-convert callback hoặc conversion chắc chắn nhìn thấy kết quả.

Nếu cần kết quả ở bước kế tiếp, hãy đặt logic vào một điểm có hợp đồng phối hợp kết quả rõ ràng.

## 4. Ví dụ callback: chuẩn hóa SKU bằng một entity mới

Ví dụ sau dùng before-convert của Spring Data MongoDB để làm rõ hợp đồng entity trả về. Mỗi public type được đặt trong một file Java riêng khi áp dụng.

`CatalogEntry` dưới đây là mô hình rút gọn cho phần minh họa. Cấu hình persistence, chọn constructor và xử lý ID của entity immutable vẫn phải phù hợp với store trong dự án thực tế.

### 4.1. Entity immutable

~~~java
import java.util.Objects;

public final class CatalogEntry {

    private final String id;
    private final String sku;

    public CatalogEntry(String id, String sku) {
        this.id = id;
        this.sku = Objects.requireNonNull(sku, "sku");
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public CatalogEntry withSku(String sku) {
        return new CatalogEntry(id, sku);
    }
}
~~~

### 4.2. Callback của store

~~~java
import java.util.Locale;

import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class NormalizeCatalogSkuCallback
        implements BeforeConvertCallback<CatalogEntry> {

    @Override
    public CatalogEntry onBeforeConvert(
            CatalogEntry entity,
            String collection) {

        String normalized = entity.getSku()
                .trim()
                .toUpperCase(Locale.ROOT);

        return entity.withSku(normalized);
    }
}
~~~

Quy tắc `trim` và chuyển chữ hoa là chính sách minh họa cho SKU. `Locale.ROOT` giúp phép chuẩn hóa kỹ thuật này không phụ thuộc locale mặc định.

Khi pipeline MongoDB tương ứng gọi callback, entity trả về có SKU mới. Object gốc không bị thay đổi.

Cần chọn before-convert vì mục tiêu là thay giá trị domain trước khi tạo document lưu trữ. Nếu document đã được tạo ở một giai đoạn muộn hơn, chỉ đổi entity chưa chắc làm document đổi theo.

### 4.3. Quan sát hợp đồng dispatch trực tiếp

Có thể minh họa phần dispatch mà không truy cập database:

~~~java
import org.springframework.data.mapping.callback.EntityCallbacks;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

public final class CallbackDispatchExample {

    public CatalogEntry normalize(CatalogEntry input) {
        EntityCallbacks callbacks = EntityCallbacks.create(
                new NormalizeCatalogSkuCallback());

        return callbacks.callback(
                BeforeConvertCallback.class,
                input,
                "catalog");
    }
}
~~~

Với input có SKU `"  sku-001  "`:

~~~text
input.getSku()   = "  sku-001  "
result.getSku()  = "SKU-001"
~~~

Đoạn này chỉ chứng minh cách gọi dispatcher và giữ entity kết quả. Nó không tự lưu dữ liệu hoặc chứng minh một repository đang dùng registry được tạo trong phương thức.

Trong ứng dụng, store cần được cấu hình để phát hiện và sử dụng callback bean theo cơ chế của module.

## 5. Ví dụ lifecycle listener: quan sát bước before-convert

Cùng module MongoDB cung cấp sự kiện `BeforeConvertEvent` và lớp hỗ trợ listener:

~~~java
import java.util.logging.Logger;

import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertEvent;
import org.springframework.stereotype.Component;

@Component
public final class CatalogLifecycleObserver
        extends AbstractMongoEventListener<CatalogEntry> {

    private static final Logger LOGGER =
            Logger.getLogger(
                    CatalogLifecycleObserver.class.getName());

    @Override
    public void onBeforeConvert(
            BeforeConvertEvent<CatalogEntry> event) {

        LOGGER.fine("Observed CatalogEntry before conversion");
    }
}
~~~

Listener này ghi nhận một điểm lifecycle. Phương thức trả `void`, không trả một entity thay thế.

Ngay cả nếu listener gọi:

~~~java
event.getSource().withSku("SKU-001");
~~~

thì lời gọi chỉ tạo một object mới trong ví dụ immutable. Nếu không có một hợp đồng khác sử dụng object đó, pipeline lưu vẫn không được yêu cầu thay source bằng object mới.

Đây là khác biệt thiết kế quan trọng giữa “tôi đã xử lý một sự kiện” và “tôi trả entity mới để bước tiếp theo sử dụng”.

### 5.1. Không khẳng định listener không thể làm thay đổi dữ liệu

Nếu event mang một entity mutable và listener chạy đồng bộ, listener có thể sửa object chung mà pipeline sau đó vẫn dùng.

Vì vậy, nói “ApplicationEvent chỉ đọc và không thể thay dữ liệu” là quá tuyệt đối.

Vấn đề là cơ chế sự kiện không cung cấp cùng hợp đồng thay entity bằng giá trị trả về như callback. Việc dựa vào mutation còn phụ thuộc object chung, thứ tự, luồng thực thi và giai đoạn conversion.

Với logic bắt buộc cần dữ liệu đã biến đổi, callback phù hợp thường thể hiện ý định rõ hơn và hỗ trợ entity immutable tốt hơn.

### 5.2. Giá trị trả về của EventListener không thay entity đang lưu

`ApplicationListener.onApplicationEvent(...)` có kiểu trả về `void`.

Với phương thức dùng `@EventListener`, một giá trị trả về có thể được framework công bố tiếp như một sự kiện theo hợp đồng của listener đó. Không nên hiểu nó là entity thay thế cho thao tác repository đang diễn ra.

Một listener trả về `CatalogEntry` không đương nhiên tương đương `BeforeConvertCallback<CatalogEntry>` trả về `CatalogEntry`.

## 6. ApplicationEvent mặc định không đồng nghĩa bất đồng bộ

Một hiểu nhầm phổ biến là event luôn chạy “ở phía sau” còn callback luôn chạy “ở phía trước”.

Cần phân biệt:

- Publication là bàn giao sự kiện cho cơ chế phát.
- Cấu hình multicaster và listener quyết định cách gọi listener.
- Callback gắn vào đường xử lý có hợp đồng riêng về kết quả.

`SimpleApplicationEventMulticaster` mặc định gọi listener đồng bộ nếu không được cấu hình executor cho việc thực thi.

Khi cấu hình executor, các listener được phép chạy bất đồng bộ có thể được giao cho executor. Không nên khẳng định mọi listener của ứng dụng đều bị chuyển sang luồng khác; một số loại listener có hợp đồng riêng.

Ngoài multicaster, ứng dụng cũng có thể dùng cơ chế bất đồng bộ cho listener. Khi đó cần xem riêng cách chuyển luồng và xử lý ngoại lệ.

### 6.1. Vì sao đổi multicaster có thể làm lộ một thiết kế sai?

Giả sử listener trước-convert đang sửa một field mutable và conversion vô tình nhìn thấy thay đổi vì mọi thứ chạy đồng bộ.

Sau khi đưa listener sang executor:

~~~text
Luồng persistence: publish → callback → convert → save
Luồng listener:                 sửa field vào một thời điểm khác
~~~

Hai luồng có thể chạy xen kẽ. Việc save nhìn thấy giá trị cũ hay mới trở thành điều không nên dựa vào.

Nếu mục tiêu là chuẩn hóa bắt buộc trước conversion, nên dùng callback phù hợp hoặc xử lý ở domain/tầng nghiệp vụ trước khi gọi persistence.

Đổi từ listener sang callback cũng không tự làm một hàm có side effect trở nên an toàn; vẫn cần kiểm soát phạm vi và tính idempotent của logic.

## 7. Thứ tự callback và thứ tự listener là hai phạm vi riêng

Callback có thể khai báo thứ tự bằng `Ordered` hoặc `@Order` theo cơ chế Spring mà hạ tầng hỗ trợ.

Trong một nhóm callback, giá trị order nhỏ hơn được ưu tiên trước. Entity trả về từ callback trước được truyền sang callback tiếp theo.

Listener cũng có cơ chế order. Tuy nhiên, không có một danh sách order chung tự trộn toàn bộ event listener với entity callback.

Ví dụ:

~~~text
listener có order = 100
callback có order = -100
~~~

không có nghĩa callback phải chạy trước điểm publication của event. Trước hết phải xét vị trí publication và vị trí dispatch trong pipeline của store.

Khi listener chạy trên executor, thứ tự được chọn để gọi hoặc bàn giao công việc cũng không bảo đảm thứ tự hoàn tất.

Nếu callback A phải tạo dữ liệu cho callback B:

1. Đặt cả hai ở đúng giai đoạn mà store hỗ trợ.
2. Xác định thứ tự rõ ràng.
3. Bảo đảm B nhận entity mà A trả về.
4. Không phụ thuộc một listener bất đồng bộ đang sửa cùng dữ liệu.

Order không khóa các thao tác save đồng thời từ nhiều request.

## 8. ReactiveEntityCallbacks không phải một event bus reactive

`ReactiveEntityCallbacks` điều phối các callback reactive và trả `Mono<T>` cho caller.

Một callback của store có thể trả một Publisher chứa entity. Pipeline sử dụng kết quả đó rồi tiếp tục bước kế tiếp.

Ví dụ MongoDB reactive, dùng cùng mô hình `CatalogEntry`:

~~~java
import java.util.Locale;

import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ReactiveNormalizeCatalogSkuCallback
        implements ReactiveBeforeConvertCallback<CatalogEntry> {

    @Override
    public Mono<CatalogEntry> onBeforeConvert(
            CatalogEntry entity,
            String collection) {

        return Mono.fromSupplier(() -> {
            String normalized = entity.getSku()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            return entity.withSku(normalized);
        });
    }
}
~~~

Implementation này phát một entity mới trong pipeline. Nó không tự subscribe và không block để lấy kết quả.

Các điều cần giữ rõ:

- Callback đồng bộ không tự biến thành callback reactive.
- Publisher phải phát entity kết quả; `Mono.empty()` không thể hiện “giữ nguyên entity” một cách đúng hợp đồng.
- Khi không thay đổi, có thể trả `Mono.just(entity)`.
- Chỉ tạo publisher chưa chứng minh công việc đã hoàn tất.
- Retry hoặc subscribe lại có thể chạy lại phần việc thuộc publisher.

Ngược lại, gọi `ApplicationEventPublisher.publishEvent(...)` trong một pipeline không tự làm toàn bộ listener trở thành một chuỗi reactive được đợi và phối hợp kết quả.

Một listener nhận event rồi tự gọi `subscribe()` đã tạo một công việc riêng. Pipeline lưu không tự đợi công việc đó và lỗi không tự trở thành lỗi của publisher lưu.

Nếu một bước bất đồng bộ bắt buộc phải hoàn tất trước khi lưu, cần nối nó vào publisher trả về ở đúng điểm tích hợp, chẳng hạn:

~~~java
return validationService.validate(entity)
        .thenReturn(entity);
~~~

Đoạn này giả định `validate` trả publisher hoàn tất khi điều kiện đã được kiểm tra. Nó minh họa composition, không tự tạo một callback hợp lệ nếu đặt ngoài interface và pipeline được store hỗ trợ.

### 8.1. Không xem ThreadLocal là context chung cho cả hai cơ chế

Listener bất đồng bộ có thể chạy ở luồng khác. Pipeline reactive cũng có thể chuyển luồng.

Vì vậy, tenant hoặc người dùng hiện tại trong một `ThreadLocal` không tự có mặt ở mọi listener hay callback.

Reactive context phải được đưa vào và đọc ở đúng ranh giới subscription. ApplicationEvent không tự sao chép context đó sang một executor bất kỳ.

Nếu listener cần thông tin để quan sát, một payload có các giá trị bất biến cần thiết thường rõ hơn việc đọc object entity đang thay đổi hoặc truy cập trạng thái ngầm.

## 9. Lỗi ở hai cơ chế được truyền theo các đường khác nhau

| Tình huống | Điều có thể xảy ra |
| --- | --- |
| Callback đồng bộ ném lỗi | Dispatch thất bại, đường persistence nhận lỗi tại điểm gọi |
| Callback reactive phát lỗi | Publisher của chuỗi nhận tín hiệu lỗi khi được thực thi |
| Listener đồng bộ ném lỗi | Tùy multicaster và ErrorHandler, lỗi có thể truyền về publisher của event |
| Listener trên executor ném lỗi | Lỗi được xử lý ở đường thực thi bất đồng bộ, không tự quay về lời gọi save |
| Lỗi xuất hiện sau bước ghi | Dữ liệu có thể đã được ghi; rollback phụ thuộc transaction thực tế |

Không nên nói mọi listener đều là “best effort” và không thể làm save thất bại. Với multicaster đồng bộ mặc định, nếu không có cơ chế xử lý lỗi thay đổi hành vi, ngoại lệ listener có thể ảnh hưởng đường publication.

Cũng không nên nói mọi lỗi callback đều làm database trở về trạng thái trước đó. Một callback trước ghi có thể ngăn bước ghi, nhưng một callback sau ghi có thể chạy khi đã có tác động persistence.

Nếu không có transaction phù hợp, báo lỗi không tự xóa một lần ghi đã hoàn tất.

### 9.1. Nuốt lỗi có thể làm mất một quy tắc bắt buộc

Ví dụ, listener chuẩn hóa SKU bị lỗi nhưng multicaster được cấu hình chỉ ghi log rồi tiếp tục. Ứng dụng có thể lưu dữ liệu chưa chuẩn hóa.

Nếu chuẩn hóa là điều kiện bắt buộc, cần đặt logic ở một điểm có hợp đồng thất bại rõ ràng, đồng thời bảo đảm mọi đường ghi cần thiết đều tuân theo quy tắc.

Callback cũng không thay thế invariant của domain. Bulk update hoặc đường truy cập trực tiếp có thể không đi qua cùng callback, nên các ràng buộc quan trọng cần được bảo vệ ở các tầng phù hợp.

### 9.2. Lỗi sau ghi có thể dẫn đến retry

Caller có thể nhận lỗi và thử lại dù lần ghi đầu đã có tác động.

Vì vậy, các side effect như gửi thông báo, tăng bộ đếm bên ngoài hoặc tạo tài nguyên không nên được xem là tự động “đúng một lần” chỉ vì chúng nằm trong callback hoặc listener.

Cần thiết kế idempotency, deduplication và transaction theo yêu cầu thực tế.

## 10. After-save, after-commit và thông báo nghiệp vụ

Ba khái niệm này cần được tách riêng:

| Điểm | Câu hỏi mà nó trả lời |
| --- | --- |
| After-save của store | Thao tác đã đến giai đoạn sau lưu theo pipeline của module chưa? |
| After-commit của transaction | Transaction thực tế đã commit thành công chưa? |
| Sự kiện nghiệp vụ | Điều gì đã xảy ra ở mức nghiệp vụ và ai cần biết? |

Một `AfterSaveEvent` không tự bảo đảm transaction ứng dụng đã commit. Callback after-save cũng không có bảo đảm đó.

Ví dụ:

~~~text
Bắt đầu transaction
    → lưu CatalogEntry
    → after-save callback hoặc event
    → lưu một dữ liệu khác
    → lỗi
    → rollback transaction
~~~

Nếu listener đã gọi dịch vụ bên ngoài, rollback database không tự thu hồi tác động đó.

### 10.1. TransactionalEventListener là một cơ chế khác

Nếu ứng dụng cần xử lý một sự kiện sau commit, có thể dùng listener gắn với transaction completion.

Payload minh họa:

~~~java
public final class CatalogEntrySaved {

    private final String entryId;

    public CatalogEntrySaved(String entryId) {
        this.entryId = entryId;
    }

    public String getEntryId() {
        return entryId;
    }
}
~~~

Listener minh họa cho một ứng dụng dùng transaction imperative:

~~~java
import java.util.logging.Logger;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public final class CommittedCatalogObserver {

    private static final Logger LOGGER =
            Logger.getLogger(
                    CommittedCatalogObserver.class.getName());

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onCatalogEntrySaved(CatalogEntrySaved event) {
        LOGGER.fine("Observed committed catalog operation");
    }
}
~~~

Để ví dụ có ý nghĩa:

1. Ứng dụng phải thực sự công bố `CatalogEntrySaved`; save entity không tự tạo custom event này.
2. Publication phải diễn ra trong một transaction được hạ tầng phù hợp nhận biết.
3. Store và transaction manager phải được cấu hình đúng.
4. Không có transaction phù hợp thì listener không tự chạy như một listener thông thường; `fallbackExecution` có quy tắc riêng và mặc định không bật.

Đây là cơ chế transaction-bound event, không phải tính chất tự có của lifecycle `ApplicationEvent`.

Với reactive transaction, cần xem khả năng hỗ trợ và cách truyền transaction context của phiên bản Spring Framework cùng cơ chế publication đang dùng. Không áp dụng nguyên giả định transaction gắn với thread sang reactive.

### 10.2. After-commit chưa giải quyết độ bền của việc gửi thông báo

Nếu process dừng sau commit nhưng trước khi gửi thông báo, dữ liệu có thể đã lưu còn thông báo chưa được gửi.

Nếu việc phát thông báo phải có khả năng phục hồi, có thể dùng outbox: ghi nhận yêu cầu phát cùng dữ liệu trong transaction, rồi xử lý gửi bằng một thành phần riêng.

Outbox vẫn cần chính sách retry và xử lý trùng. Không nên biến “dùng event” thành một lời hứa gửi chính xác một lần mà hệ thống chưa cung cấp.

## 11. Không đồng nhất lifecycle event với domain event

Lifecycle event mô tả bước kỹ thuật, chẳng hạn entity sắp được chuyển đổi hoặc đã đi qua bước lưu.

Domain event mô tả một sự kiện nghiệp vụ, chẳng hạn:

~~~text
ProductActivated
OrderConfirmed
ReservationCancelled
~~~

Một entity có thể được save nhiều lần mà không phải lần nào cũng tương ứng một sự kiện nghiệp vụ mới.

Ngược lại, “đã lưu một Order” không tự có nghĩa “đã xác nhận Order”.

Spring Data có cơ chế publication domain event từ aggregate theo các API được hỗ trợ, nhưng cơ chế này vẫn khác với callback và mapping event. Không tự suy ra domain event luôn được công bố sau commit.

Nếu chuyển logic gửi “đơn đã xác nhận” vào listener của mọi after-save, ứng dụng có thể gửi thông báo cả khi chỉ cập nhật một ghi chú.

Nên xác định rõ nơi quyết định trạng thái nghiệp vụ, payload cần công bố và yêu cầu về transaction.

## 12. Phạm vi store và đường thao tác là điều kiện bắt buộc

| Hạ tầng | Ranh giới cần nhớ |
| --- | --- |
| Spring Data Commons | Có abstraction callback dùng chung; không áp đặt mọi lifecycle event cho mọi module |
| Spring Data MongoDB | Có mapping event và callback tại những điểm được tích hợp; ví dụ trong bài thuộc phạm vi này |
| Spring Data JDBC | Có lifecycle infrastructure cho aggregate; cần xem điểm phát event và callback của module |
| Spring Data R2DBC | Có callback reactive; không tự suy rằng có cùng event hoặc cùng đường gọi với JDBC |
| Spring Data JPA | Lifecycle của JPA provider như `@PrePersist` khác với dispatch callback Commons và Spring application event |
| Module khác | Kiểm tra interface, loại event và thao tác được hỗ trợ ở phiên bản thực tế |

Cũng cần phân biệt các đường thao tác bên trong cùng module:

- Save hoặc insert một entity.
- Update trực tiếp bằng điều kiện.
- Bulk operation.
- Delete theo entity, ID hoặc query.
- Đọc entity đầy đủ.
- Đọc DTO hoặc projection.
- Truy cập bằng template hay driver trực tiếp.

Một update không materialize từng entity không nhất thiết có điểm để gọi callback chuyển đổi entity.

Một driver operation viết tay cũng không tự đi qua lifecycle infrastructure của repository.

Callback hay event có thể được thiết kế quanh aggregate root. Không mặc định mỗi object lồng nhau đều nhận một lần dispatch độc lập.

Vì vậy, không chọn cơ chế chỉ dựa vào việc đã thấy một log từ một lần save. Cần kiểm chứng đúng những đường ứng dụng thực sự dùng.

## 13. Liên hệ với repository, derived query và auditing

### 13.1. Giữ entity trả về từ repository

Callback có thể tạo bản sao entity. Persistence cũng có thể trả entity mang ID, version hoặc dữ liệu được xử lý tiếp.

Caller nên tiếp tục với kết quả save:

~~~java
CatalogEntry saved = repository.save(input);
~~~

Không mặc định `input` luôn chứa mọi thay đổi sau save.

Với reactive, giữ entity mà publisher của repository trả về. Việc dùng `thenReturn(input)` sau save có thể làm caller nhận lại object cũ và bỏ mất kết quả pipeline.

Một event listener nhìn thấy source nào và ở giai đoạn nào cũng cần được xác định theo store. Không nên so log của một event trước-convert với entity trả về sau-save rồi kết luận callback không hoạt động.

### 13.2. Derived query và Query by Example

Callback chuẩn hóa SKU trước ghi không tự chuẩn hóa tham số của `findBySku(...)`.

Tương tự, một probe của Query by Example không mặc nhiên đi qua callback trước lưu.

Nếu ghi dữ liệu theo một quy tắc chuẩn hóa, đường tìm kiếm cần áp dụng cùng hợp đồng khi phù hợp. Có thể tách quy tắc thành một hàm thuần rồi dùng ở callback và ở tầng chuẩn bị query.

Lifecycle event cũng không tự biến tham số query thành dữ liệu đã chuẩn hóa.

### 13.3. Phân trang và sắp xếp

Nếu callback tạo field dùng để sort khi ghi, dữ liệu cũ vẫn có thể chưa có field hoặc chưa được chuẩn hóa.

`Pageable` và `Sort` không tự sửa sự không nhất quán đó. Chúng cũng không tạo index và không bảo đảm thứ tự ổn định nếu khóa sort có nhiều giá trị trùng.

Một listener bổ sung dữ liệu sau khi query trả về không làm database đã sắp xếp theo giá trị bổ sung đó.

### 13.4. Projection

Query trả projection hoặc DTO có thể đi qua đường mapping khác với query trả entity đầy đủ.

Không mặc định một callback hoặc lifecycle listener của entity sẽ chạy cho mọi dạng projection.

Nếu một phép biến đổi là yêu cầu của DTO, cần xác định vị trí mapping DTO rõ ràng, thay vì chỉ dựa vào lifecycle của entity lưu trữ.

### 13.5. Auditing

Auditing có thể sử dụng callback hoặc lifecycle infrastructure riêng của store.

Không nên vừa bật auditing vừa tự cập nhật cùng field trong event listener mà chưa xác định thứ tự và trách nhiệm.

Khi cần giá trị như thời điểm tạo hoặc người sửa trước một bước xử lý khác, hãy kiểm tra giai đoạn và order của auditing ở module thực tế. Không sao chép giả định từ module khác.

Việc entity có `@CreatedDate` cũng không tự chứng minh auditing đã được bật.

## 14. Chọn cơ chế theo kết quả cần bảo đảm

| Nhu cầu | Hướng phù hợp khi được hạ tầng hỗ trợ |
| --- | --- |
| Chuẩn hóa field trước conversion | Callback before-convert hoặc quy tắc domain trước persistence |
| Thay entity immutable cho bước tiếp theo | Entity callback trả entity mới |
| Kiểm tra bắt buộc trước một bước persistence | Callback đúng giai đoạn hoặc validation ở tầng nghiệp vụ |
| Quan sát lifecycle để chẩn đoán | Listener của lifecycle event, với cách xử lý lỗi rõ ràng |
| Chờ một bước reactive trước lưu | Callback reactive hoặc composition trong publisher của tầng nghiệp vụ |
| Chạy khi transaction commit thành công | Cơ chế transaction completion hoặc transaction-bound listener |
| Phát sự kiện nghiệp vụ | Publication được quyết định ở nơi có đủ ngữ cảnh nghiệp vụ |
| Gửi thông báo có khả năng phục hồi sau commit | Thiết kế outbox cùng cơ chế retry và xử lý trùng |
| Bảo vệ invariant trên mọi đường ghi | Domain, validation và ràng buộc store phù hợp; không chỉ một callback |

Không cần chuyển mọi event listener thành callback. Nếu listener chỉ quan sát và không phải điều kiện của bước tiếp theo, nó có thể phù hợp với mục tiêu đó.

Ngược lại, không dùng event bất đồng bộ như một cách tránh chờ một công việc bắt buộc. Việc tách công việc khỏi pipeline là thay đổi hợp đồng xử lý, không chỉ tối ưu hiệu năng.

### 14.1. Khi chuyển logic từ listener sang callback

Một trình tự hữu ích:

1. Xác định logic đang quan sát hay đang biến đổi dữ liệu bắt buộc.
2. Chọn giai đoạn callback có đủ đầu vào và diễn ra trước bước cần kết quả.
3. Tách quy tắc thuần khỏi adapter listener cũ.
4. Cài callback có kiểu entity cụ thể, trả entity kết quả.
5. Loại bỏ đường áp dụng cùng quy tắc ở listener nếu không còn cần.
6. Kiểm chứng những đường persistence thực tế, gồm cả đường có thể bỏ qua callback.

Không giữ cả listener cũ và callback mới cùng làm một việc rồi mặc định framework sẽ tự loại trùng.

Nếu listener trước đây tạo side effect ngoài database, việc chuyển sang callback không tự thay đổi tính chất transaction của side effect đó.

## 15. Kiểm chứng sự khác biệt thay vì chỉ đếm log

Bảng sau phân tách các kết luận cần kiểm chứng:

| Kịch bản | Cần quan sát |
| --- | --- |
| Callback trả bản sao immutable | Pipeline sử dụng bản sao, object đầu vào giữ nguyên |
| Listener gọi một phương thức tạo bản sao | Không tự suy ra source được thay thế |
| Listener đồng bộ sửa object mutable | Xác định rõ mutation có xảy ra trước conversion ở đường này hay không |
| Listener được đưa sang executor | Persistence không dựa vào thời điểm listener hoàn tất |
| Nhiều callback cùng giai đoạn | Callback sau nhận kết quả callback trước theo order |
| Listener và callback có order khác nhau | Không suy ra một thứ tự chung ngoài pipeline store |
| Listener đồng bộ ném lỗi | Kiểm tra ErrorHandler và lỗi ở lời gọi persistence |
| Listener bất đồng bộ ném lỗi | Xác định đường ghi nhận lỗi, không mặc định caller save nhận được |
| Reactive callback trả entity | Entity tiếp tục trong cùng publisher |
| Có retry | Quy tắc và side effect không tạo tác động lặp ngoài hợp đồng |
| After-save xảy ra rồi transaction rollback | Không nhầm lifecycle completion với commit |
| Custom event phát ngoài transaction | Không mặc định listener after-commit sẽ chạy |
| Update trực tiếp hoặc bulk | Xác định có đi qua callback hay event đang dùng không |
| Đổi cấu hình auditing | Không áp dụng trùng logic cập nhật field |

Có ba mức kiểm chứng:

- **Dispatch:** entity đầu vào, entity đầu ra, kiểu callback và thứ tự.
- **Tích hợp store:** event và callback thực sự được gọi ở API nào, dữ liệu nào được lưu.
- **Transaction và bất đồng bộ:** lỗi, rollback, executor, subscription và tác động bên ngoài.

Một kiểm tra gọi trực tiếp `onBeforeConvert(...)` không chứng minh hạ tầng khám phá bean hoặc thứ tự event/callback.

Một log “đã nhận after-save” cũng không chứng minh transaction đã commit.

Các đoạn mã trong bài là ví dụ minh họa để áp dụng và kiểm chứng trong dự án. Chúng không phải báo cáo đã chạy kiểm thử hoặc xác nhận một cấu hình store cụ thể.

## 16. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Callback trả entity mới nhưng caller vẫn thấy cũ | Bỏ qua giá trị trả về từ callback hoặc save | Tiếp tục với entity kết quả |
| Listener chạy nhưng object immutable không đổi | Chỉ tạo bản sao rồi bỏ đi | Dùng callback phù hợp nếu cần thay entity trong pipeline |
| Dữ liệu lúc đúng lúc sai sau đổi executor | Listener mutation chạy xen kẽ với persistence | Bỏ phụ thuộc vào listener bất đồng bộ cho bước bắt buộc |
| Đổi order không làm callback vượt lên trước event | Hai cơ chế có vị trí pipeline và phạm vi order khác nhau | Kiểm tra điểm publication và dispatch của module |
| Save trả lỗi nhưng dữ liệu đã tồn tại | Lỗi sau ghi hoặc không có rollback tương ứng | Xác định giai đoạn lỗi và transaction thực tế |
| Save thành công nhưng tác vụ phụ reactive chưa xong | Listener hoặc callback subscribe nội bộ | Nối tác vụ cần đợi vào pipeline hoặc thiết kế xử lý nền rõ ràng |
| Thông báo đã gửi dù transaction rollback | Dùng after-save như after-commit | Chọn transaction-bound handling hoặc outbox phù hợp |
| Listener after-commit không chạy | Không có transaction, event chưa được phát hoặc context không phù hợp | Kiểm tra publication và hạ tầng transaction |
| Quy tắc chạy lặp | Cùng logic trong event và callback, retry hoặc nhiều lần subscription | Tách trách nhiệm, loại trùng và thiết kế idempotency |
| Bulk update bỏ qua chuẩn hóa | Đường thao tác không materialize entity theo pipeline callback | Bổ sung quy tắc cho đường ghi đó hoặc dùng ràng buộc phù hợp |

Trước khi sửa, hãy xác định câu hỏi cụ thể:

~~~text
Ai gọi?
Ở giai đoạn nào?
Chạy trong luồng hoặc subscription nào?
Ai sử dụng kết quả?
Transaction đã kết thúc chưa?
~~~

Các câu hỏi này giúp tìm đúng ranh giới sai, thay vì thêm một listener hoặc một callback nữa mà chưa biết đường thực thi.

## 17. Tự kiểm tra kiến thức

**EntityCallback và lifecycle ApplicationEvent có thể cùng tồn tại không?**

Có, nếu module có cả hai điểm tích hợp. Cần xem thứ tự của store và tránh áp dụng cùng quy tắc hai lần.

**ApplicationEvent có luôn bất đồng bộ không?**

Không. Multicaster mặc định thường gọi listener đồng bộ. Executor và cấu hình listener có thể thay đổi cách thực thi.

**Vì sao callback phù hợp với entity immutable?**

Vì callback có hợp đồng trả entity thay thế để bước tiếp theo sử dụng. Listener không mặc nhiên thay source bằng giá trị trả về.

**Listener có thể sửa entity mutable không?**

Có thể, nếu nó nắm object chung. Nhưng khả năng đó phụ thuộc giai đoạn và cách thực thi, không tương đương hợp đồng biến đổi của callback.

**Đặt order nhỏ cho callback có làm nó chạy trước mọi event listener không?**

Không. Trước hết phải xem vị trí event publication và callback dispatch. Order không hợp nhất mọi cơ chế thành một danh sách.

**Lifecycle ApplicationEvent có trở thành reactive khi được phát từ một Mono không?**

Không tự động. Publication không tự phối hợp Publisher của listener với pipeline đang lưu entity.

**AfterSaveEvent hoặc after-save callback có chứng minh transaction đã commit không?**

Không. Transaction có thể vẫn tiếp tục và có thể rollback ở bước sau.

**Điều gì cần nhớ khi chọn giữa hai cơ chế?**

Xác định kết quả cần được bảo đảm: biến đổi entity cho bước kế tiếp, quan sát một lifecycle hay xử lý sau commit. Sau đó chọn đúng điểm tích hợp, cách thực thi và phạm vi hỗ trợ của store.
