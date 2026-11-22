# Viết listener bằng ApplicationListener và AbstractRepositoryEventListener

Spring Data REST phát các repository events trong quá trình xử lý tài nguyên được export. Ứng dụng có thể lắng nghe các event này để chuẩn hóa entity, ghi nhận thay đổi hoặc kích hoạt công việc phụ trợ. Hai cách triển khai phổ biến là dùng Spring `ApplicationListener<E>` cho một event cụ thể và kế thừa `AbstractRepositoryEventListener<T>` để nhận nhiều loại repository event qua các callback.

Cả hai cách đều tham gia Spring application event mechanism. Khác biệt chính nằm ở cách chọn event và cách tổ chức code: `ApplicationListener` nhận event class được khai báo trong generic type; `AbstractRepositoryEventListener` tự phân phối repository event đến các hook như `onBeforeSave` và `onAfterSave`.

## 1. Các repository event của Spring Data REST

Spring Data REST phát event quanh các thao tác CRUD và association. Những event thường dùng gồm:

| Event | Thời điểm |
|---|---|
| `BeforeCreateEvent` | Trước khi tạo entity mới |
| `AfterCreateEvent` | Sau thao tác tạo entity |
| `BeforeSaveEvent` | Trước khi lưu entity |
| `AfterSaveEvent` | Sau khi repository save trả về |
| `BeforeLinkSaveEvent` | Trước khi lưu association |
| `AfterLinkSaveEvent` | Sau khi lưu association |
| `BeforeLinkDeleteEvent` | Trước khi xóa association |
| `AfterLinkDeleteEvent` | Sau khi xóa association |
| `BeforeDeleteEvent` | Trước khi xóa entity |
| `AfterDeleteEvent` | Sau thao tác xóa entity |

Ví dụ, khi client cập nhật một item resource bằng PUT hoặc PATCH, luồng thường phát `BeforeSaveEvent` trước thao tác save và `AfterSaveEvent` sau khi repository save trả về. POST tạo entity mới đi qua Create event; thao tác trên association có Link event riêng.

Các event này là hook của luồng Spring Data REST. Một controller tùy chỉnh tự gọi repository không mặc nhiên phát cùng các Spring Data REST repository events. Nếu cần cùng hành vi ở nhiều đường ghi, hãy đặt nghiệp vụ dùng chung ở service/domain layer và gọi service đó từ các entry point phù hợp.

## 2. Cách thứ nhất: triển khai ApplicationListener

`ApplicationListener<E>` là interface của Spring để nhận một loại application event. Khi khai báo generic là `BeforeSaveEvent`, listener được đăng ký để nhận event trước khi lưu entity.

Ví dụ listener chỉ xử lý `Person`:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.event.BeforeSaveEvent;

@Component
public class PersonBeforeSaveListener
        implements ApplicationListener<BeforeSaveEvent> {

    @Override
    public void onApplicationEvent(BeforeSaveEvent event) {
        Object source = event.getSource();

        if (!(source instanceof Person)) {
            return;
        }

        Person person = (Person) source;
        person.setDisplayName(
            person.getDisplayName().trim()
        );
    }
}
```

Điểm đáng chú ý:

- Generic type `BeforeSaveEvent` xác định loại event mà listener quan tâm.
- `event.getSource()` trả về đối tượng entity gắn với event; kiểu trả về cần được kiểm tra trước khi cast.
- Một `BeforeSaveEvent` có thể liên quan đến nhiều domain type được export. Kiểm tra `instanceof` giúp listener chỉ áp dụng cho entity mà nó phụ trách.
- Method `onApplicationEvent` là nơi đặt xử lý cho event đó.

Để nhận `AfterSaveEvent`, tạo listener riêng có generic type tương ứng:

```java
@Component
public class PersonAfterSaveListener
        implements ApplicationListener<AfterSaveEvent> {

    @Override
    public void onApplicationEvent(AfterSaveEvent event) {
        Object source = event.getSource();

        if (!(source instanceof Person)) {
            return;
        }

        Person person = (Person) source;
        // Ghi nhận thông tin sau khi repository save trả về.
    }
}
```

Không thể khai báo cùng một class triển khai đồng thời `ApplicationListener<BeforeSaveEvent>` và `ApplicationListener<AfterSaveEvent>` như hai interface generic khác nhau vì Java type erasure làm hai chữ ký có cùng erasure. Tách thành hai bean cụ thể thường rõ ràng hơn. Nếu muốn một điểm nhận nhiều event, có thể lắng nghe kiểu event chung và phân nhánh bằng `instanceof`, nhưng cần giữ phạm vi event hẹp và xử lý từng loại rõ ràng.

## 3. Cách thứ hai: kế thừa AbstractRepositoryEventListener

`AbstractRepositoryEventListener<T>` là lớp trừu tượng đã triển khai `ApplicationListener<RepositoryEvent>`. Lớp này nhận repository event rồi phân phối theo loại event đến các protected callback. Thay vì tự viết một `onApplicationEvent` dài với nhiều nhánh, ứng dụng chỉ override những hook cần thiết.

Ví dụ:

```java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class PersonRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        if (!(entity instanceof Person)) {
            return;
        }

        Person person = (Person) entity;
        person.setDisplayName(
            person.getDisplayName().trim()
        );
    }

    @Override
    protected void onAfterSave(Object entity) {
        if (!(entity instanceof Person)) {
            return;
        }

        Person person = (Person) entity;
        // Ghi nhận hoặc phát application event sau save.
    }
}
```

Ở ví dụ này, listener dùng `Object` và kiểm tra kiểu entity tường minh. Cách này an toàn khi listener cần quan sát nhiều domain type hoặc muốn tự kiểm soát việc lọc entity. Nếu dùng generic type cụ thể như `AbstractRepositoryEventListener<Person>`, hãy xác nhận hành vi lọc type của phiên bản Spring Data REST đang chạy; không dựa vào generic compile-time như một cơ chế authorization hay validation.

Các callback có sẵn gồm:

| Callback | Event được phân phối |
|---|---|
| `onBeforeCreate(T entity)` | `BeforeCreateEvent` |
| `onAfterCreate(T entity)` | `AfterCreateEvent` |
| `onBeforeSave(T entity)` | `BeforeSaveEvent` |
| `onAfterSave(T entity)` | `AfterSaveEvent` |
| `onBeforeLinkSave(T parent, Object linked)` | `BeforeLinkSaveEvent` |
| `onAfterLinkSave(T parent, Object linked)` | `AfterLinkSaveEvent` |
| `onBeforeLinkDelete(T parent, Object linked)` | `BeforeLinkDeleteEvent` |
| `onAfterLinkDelete(T parent, Object linked)` | `AfterLinkDeleteEvent` |
| `onBeforeDelete(T entity)` | `BeforeDeleteEvent` |
| `onAfterDelete(T entity)` | `AfterDeleteEvent` |

Với các hook association, `parent` là entity cha và `linked` là đối tượng được liên kết. Cặp tham số này hữu ích khi cần ghi nhận ai được gắn hoặc gỡ khỏi quan hệ.

Không cần override mọi callback. Chỉ triển khai những event ứng dụng thực sự cần xử lý; các hook còn lại có thể để mặc định.

## 4. So sánh hai cách triển khai

| Tiêu chí | ApplicationListener | AbstractRepositoryEventListener |
|---|---|---|
| Cách đăng ký | Implement `ApplicationListener<EventType>` | Kế thừa lớp listener trừu tượng |
| Phạm vi event | Thường tập trung một event type cho mỗi listener | Nhiều repository event qua các callback |
| Điểm xử lý | `onApplicationEvent(event)` | `onBeforeSave`, `onAfterSave` và các hook khác |
| Phân nhánh event | Tự viết nếu nhận event type chung | Lớp cha dispatch theo event type |
| Lọc entity | Tự kiểm tra source khi cần | Dùng generic type và/hoặc kiểm tra entity tường minh tùy phiên bản/cách triển khai |
| Phù hợp khi | Chỉ quan tâm một event cụ thể hoặc cần kiểm soát event API trực tiếp | Muốn gom nhiều callback CRUD/association vào một listener |

Dùng `ApplicationListener` khi xử lý một event riêng biệt và muốn code thể hiện rõ loại event ngay ở khai báo class. Dùng `AbstractRepositoryEventListener` khi cần một listener có nhiều hook lifecycle và muốn tránh tự dispatch từng event.

Cả hai đều là Spring bean. Thêm `@Component` hoặc đăng ký bean bằng cấu hình để Spring quản lý listener. Nếu bean không nằm trong application context hoặc package không được component scan, event sẽ không đến listener.

## 5. Lọc đúng domain type

Một ứng dụng Spring Data REST thường export nhiều repository. Vì vậy, listener nhận event cần xử lý đúng entity type.

Với `ApplicationListener<BeforeSaveEvent>`, source của event nên được kiểm tra trước khi cast:

```java
if (!(event.getSource() instanceof Person)) {
    return;
}

Person person = (Person) event.getSource();
```

Với `AbstractRepositoryEventListener`, có thể chọn generic type cụ thể nếu listener chỉ phụ trách một domain type và phiên bản framework hỗ trợ việc xác định type đó. Nếu listener dùng `Object` để nhận nhiều loại entity, luôn kiểm tra kiểu trong callback trước khi truy cập field.

Không dùng tên repository hoặc URL để suy ra kiểu object tại runtime nếu event đã cung cấp source entity. Kiểm tra kiểu trực tiếp rõ ràng và ít phụ thuộc cấu trúc endpoint hơn.

Lọc type cũng không phải kiểm tra quyền. Listener chỉ quyết định có áp dụng logic cho entity nào; authentication và authorization vẫn phải được thực hiện ở Spring Security hoặc lớp nghiệp vụ phù hợp.

## 6. Khi nào chọn listener thay cho @RepositoryEventHandler?

Spring Data REST còn cung cấp cách khai báo handler bằng `@RepositoryEventHandler` và các annotation như `@HandleBeforeSave`, `@HandleAfterSave`. Cách này dùng một POJO với method handler được đánh dấu, và cho phép gắn domain type ở annotation để framework lọc handler theo loại entity.

Ba cách có thể được lựa chọn theo nhu cầu:

- `ApplicationListener`: phù hợp khi cần nhận trực tiếp một event class của Spring.
- `AbstractRepositoryEventListener`: phù hợp khi muốn override một nhóm lifecycle callback trong cùng class.
- `@RepositoryEventHandler`: phù hợp khi muốn khai báo handler theo annotation trên các method và lọc theo domain type.

Không nên đăng ký nhiều cơ chế cùng thực hiện một side effect cho cùng event nếu chưa kiểm soát việc chúng cùng được gọi. Ví dụ, nếu một email được gửi từ cả `ApplicationListener` và `@HandleAfterSave`, một lần update có thể gửi hai email.

## 7. Thứ tự thực thi, transaction và side effect

Spring application events thường được xử lý đồng bộ trong thread phát event theo cấu hình mặc định. Ứng dụng có thể tùy chỉnh event multicaster hoặc listener execution; nếu có xử lý bất đồng bộ, thứ tự và transaction context có thể khác. Không nên dựa vào thứ tự giữa nhiều listener nếu chưa cấu hình và kiểm thử rõ ràng.

`AfterSaveEvent` có nghĩa repository save đã trả về; nó không tự chứng minh transaction bên ngoài đã commit. Nếu cần chỉ chạy tác vụ sau commit, dùng transaction-aware listener như `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` khi event được phát trong transaction phù hợp, hoặc thiết kế transactional outbox cho message cần độ tin cậy cao.

Một số nguyên tắc:

1. Giữ callback ngắn và tránh gọi dịch vụ mạng kéo dài trong request thread.
2. Không gửi email, thanh toán hoặc phát message không thể đảo ngược trước khi hiểu transaction boundary.
3. Thiết kế side effect để chịu được retry hoặc event trùng.
4. Dùng outbox và consumer deduplication nếu cần bảo đảm phát message bền vững.
5. Nếu listener ném exception, response và rollback phụ thuộc event được phát ở đâu, transaction boundary và exception policy; cần kiểm thử với cấu hình thực tế.

Listener là extension point của lifecycle, không phải hàng đợi nền tự động. Nếu tác vụ tốn thời gian, hãy phát một event/application command phù hợp và chuyển phần xử lý sang cơ chế async hoặc messaging có quản lý lỗi.

## 8. Kiểm thử listener

Unit test gọi trực tiếp callback chỉ kiểm tra logic bên trong method. Nó không chứng minh Spring đã đăng ký bean hoặc Spring Data REST phát event trong request thật.

Nên có integration test qua endpoint hoặc test context tương ứng:

- PUT/PATCH một entity: xác nhận before-save và after-save được gọi đúng.
- POST entity mới: xác nhận Create event, không nhầm với Save event.
- Thay đổi association: xác nhận LinkSave hoặc LinkDelete callback.
- Gửi event với entity type khác: xác nhận listener bỏ qua khi không thuộc phạm vi.
- Listener before-save từ chối hoặc ném exception: xác nhận request không hoàn tất như một lần ghi thành công.
- After-save phát application event: xác nhận hành vi transaction và side effect.
- Nếu cấu hình async hoặc nhiều listener: kiểm tra thứ tự, lỗi và transaction context theo cấu hình đó.

Có thể dùng spy/mock bean để xác nhận callback được gọi, nhưng nên kiểm tra thêm trạng thái repository cuối cùng để bảo đảm listener không chỉ chạy mà còn tạo ra kết quả mong muốn.

## 9. Checklist triển khai

1. Xác định event cụ thể cần xử lý: create, save, link save/delete hay delete.
2. Dùng `ApplicationListener<EventType>` nếu chỉ cần nhận một event class trực tiếp.
3. Dùng `AbstractRepositoryEventListener<T>` nếu muốn override nhiều callback repository lifecycle.
4. Đăng ký listener thành Spring bean trong application context.
5. Kiểm tra source entity trước khi cast và giới hạn xử lý đúng domain type.
6. Không đăng ký nhiều listener cùng thực hiện một side effect ngoài ý muốn.
7. Phân biệt repository save hoàn tất với transaction commit.
8. Dùng after-commit listener hoặc outbox khi tác vụ ngoài cần chạy sau commit.
9. Kiểm thử listener qua request Spring Data REST thực tế, bao gồm entity type khác và lỗi handler.

`ApplicationListener` cho phép xử lý trực tiếp một loại Spring event; `AbstractRepositoryEventListener` cung cấp các callback có sẵn cho nhiều repository lifecycle event. Chọn cách phù hợp với số event cần theo dõi, lọc entity rõ ràng và kiểm soát transaction/side effect sẽ giúp listener trong Spring Data REST dễ bảo trì và dự đoán hơn.
