# Event có generic type trong Spring

Generic event cho phép một loại sự kiện đại diện cho nhiều kiểu dữ liệu khác nhau. Ví dụ, cùng một họ sự kiện EntityCreatedEvent có thể mang Person hoặc Organization. Listener có thể khai báo kiểu cụ thể mà nó quan tâm, để Spring định tuyến sự kiện theo cả lớp event lẫn tham số generic.

Điểm cần xử lý là Java dùng type erasure: tham số generic thường không còn hiện diện đầy đủ trên instance ở runtime. Spring có ResolvableType để biểu diễn kiểu generic và ResolvableTypeProvider để event cung cấp metadata kiểu của chính nó. Khi khai báo đúng metadata, các listener có thể nhận đúng biến thể generic mà không cần tự kiểm tra instanceof hoặc viết nhiều nhánh điều kiện.

## 1. Vì sao cần generic event?

Giả sử ứng dụng có hai loại dữ liệu Person và Organization. Khi một entity được tạo, các module khác nhau có thể muốn phản ứng:

- Module hồ sơ xử lý khi một Person được tạo.
- Module tổ chức xử lý khi một Organization được tạo.
- Module audit ghi nhận mọi entity được tạo.

Nếu tạo riêng PersonCreatedEvent và OrganizationCreatedEvent, mỗi event có lớp và listener riêng. Cách đó rõ ràng và phù hợp khi hai sự kiện có ngữ nghĩa khác nhau.

Nếu hai sự kiện thực sự cùng biểu đạt một hành động và chỉ khác kiểu payload, có thể mô hình hóa bằng một lớp generic:

- EntityCreatedEvent<Person>
- EntityCreatedEvent<Organization>

Cách này giảm số lớp event và làm rõ rằng cả hai đều là biến thể của cùng một hợp đồng. Một listener cụ thể có thể khai báo EntityCreatedEvent<Person>, trong khi listener tổng quát có thể xử lý mọi EntityCreatedEvent.

Không nên dùng generic chỉ để giảm số lượng class. Nếu PersonCreated và OrganizationCreated có quy tắc nghiệp vụ, dữ liệu hoặc vòng đời khác nhau đáng kể, hai event riêng có thể dễ đọc và an toàn hơn.

## 2. Vấn đề type erasure của Java

Ở thời điểm biên dịch, trình biên dịch biết kiểu T trong EntityCreatedEvent<T>. Vì vậy, câu lệnh sau có thể suy luận T là Person:

~~~java
Person person = new Person(10L, "An");
EntityCreatedEvent<Person> event =
    new EntityCreatedEvent<>(this, person);
~~~

Nhưng ở runtime, Java không tạo hai lớp riêng biệt cho EntityCreatedEvent<Person> và EntityCreatedEvent<Organization>. Cả hai instance đều có cùng lớp runtime EntityCreatedEvent. Gọi getClass() chỉ cho biết lớp thô, không đủ để khẳng định tham số generic ban đầu là Person hay Organization.

Điều này có nghĩa là nếu Spring chỉ nhìn thấy lớp event thô, nó không có đủ thông tin để phân biệt các listener chỉ khác nhau ở tham số generic. Ví dụ, listener cho EntityCreatedEvent<Person> và listener cho EntityCreatedEvent<Organization> có thể không được lọc như mong đợi nếu event không cung cấp metadata generic.

Để giải quyết, event cần cung cấp kiểu đầy đủ ở runtime.

## 3. ResolvableType và ResolvableTypeProvider

Spring dùng ResolvableType để biểu diễn một kiểu Java, bao gồm cả tham số generic. ResolvableType có thể biểu diễn kiểu thô, tham số kiểu, kiểu lồng nhau và quan hệ gán được giữa các kiểu.

Một số API hữu ích:

- ResolvableType.forClass(MyEvent.class): tạo mô tả cho một lớp.
- ResolvableType.forClassWithGenerics(...): tạo mô tả cho lớp cùng các tham số generic.
- ResolvableType.forInstance(object): suy ra mô tả kiểu từ một instance.
- getGeneric(): truy cập tham số generic.
- resolve(): lấy lớp Java tương ứng khi có thể phân giải.

ResolvableTypeProvider là interface cho phép một object cung cấp ResolvableType của nó. Với generic event, event triển khai interface này và trả về lớp event cùng kiểu payload thực tế.

Spring có thể dùng metadata này để so khớp kiểu event với kiểu tham số của phương thức @EventListener. Listener khai báo EntityCreatedEvent<Person> sẽ phù hợp với event mang Person; listener khai báo EntityCreatedEvent<Organization> sẽ phù hợp với biến thể Organization.

## 4. Tạo một generic event

Ví dụ dưới đây dùng một lớp event kế thừa ApplicationEvent và triển khai ResolvableTypeProvider. Cách này giữ event là một ApplicationEvent rõ ràng và cung cấp metadata generic cho Spring.

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public final class EntityCreatedEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
            getClass(),
            ResolvableType.forInstance(entity)
        );
    }
}
~~~

Phương thức getResolvableType() là phần quan trọng:

1. ResolvableType.forInstance(entity) lấy kiểu runtime của payload.
2. ResolvableType.forClassWithGenerics(...) ghép kiểu payload vào lớp event.
3. Spring nhận được metadata như EntityCreatedEvent<Person> thay vì chỉ EntityCreatedEvent.

Ví dụ các payload có thể là record Java:

~~~java
public record Person(Long id, String name) {}

public record Organization(Long id, String name) {}
~~~

Nếu payload là Person, metadata event sẽ mô tả EntityCreatedEvent<Person>. Nếu payload là Organization, metadata sẽ mô tả EntityCreatedEvent<Organization>.

Không truyền payload null khi cần suy luận kiểu theo instance. Một giá trị null không cung cấp được lớp runtime để suy ra tham số generic; trường hợp này cần truyền metadata kiểu tường minh.

## 5. Đăng ký listener theo tham số generic

Một listener có thể khai báo chính xác biến thể event mà nó xử lý:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PersonCreatedListener {

    @EventListener
    public void handle(EntityCreatedEvent<Person> event) {
        Person person = event.getEntity();
        System.out.println("Created person: " + person.name());
    }
}
~~~

Listener khác có thể chỉ nhận Organization:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrganizationCreatedListener {

    @EventListener
    public void handle(EntityCreatedEvent<Organization> event) {
        Organization organization = event.getEntity();
        System.out.println("Created organization: " + organization.name());
    }
}
~~~

Khi event có ResolvableType đầy đủ, Spring có thể phân biệt hai phương thức listener theo tham số generic. Không cần viết một listener duy nhất rồi kiểm tra event.getEntity() instanceof Person và instanceof Organization.

Có thể có listener tổng quát nếu một xử lý áp dụng cho mọi payload:

~~~java
@Component
public class EntityAuditListener {

    @EventListener
    public void handle(EntityCreatedEvent<?> event) {
        Object entity = event.getEntity();
        System.out.println("An entity was created: " + entity);
    }
}
~~~

Dùng wildcard khi listener thực sự không cần biết kiểu cụ thể. Nếu listener cần thao tác theo API của Person hoặc Organization, khai báo tham số generic cụ thể để trình biên dịch hỗ trợ kiểm tra kiểu.

## 6. Phát generic event

Publisher dùng ApplicationEventPublisher như với event thông thường:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EntityService {

    private final ApplicationEventPublisher publisher;

    public EntityService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createPerson(Person person) {
        // Lưu person hoặc hoàn tất thao tác tạo tại đây.
        publisher.publishEvent(
            new EntityCreatedEvent<>(this, person)
        );
    }

    public void createOrganization(Organization organization) {
        // Lưu organization hoặc hoàn tất thao tác tạo tại đây.
        publisher.publishEvent(
            new EntityCreatedEvent<>(this, organization)
        );
    }
}
~~~

Dấu <> cho phép Java suy luận tham số generic từ đối số truyền vào constructor. Publisher không cần biết listener nào sẽ nhận event. Việc chọn listener dựa trên metadata kiểu được Spring phân giải.

Ví dụ trên tập trung vào cơ chế event. Trong ứng dụng thực tế, Person và Organization cần được khai báo trong dự án, còn thao tác lưu dữ liệu phải theo transaction và quy tắc nghiệp vụ của ứng dụng.

## 7. Khi payload có kiểu generic lồng nhau

Cách dùng ResolvableType.forInstance(entity) phù hợp khi tham số T có thể suy ra từ lớp runtime của payload, chẳng hạn Person hoặc Organization.

Tuy nhiên, nếu payload là List<Order>, lớp runtime thường chỉ cho biết đó là ArrayList hoặc List. Do type erasure, instance không tự cho biết phần tử bên trong là Order. ResolvableType.forInstance(orders) không thể khôi phục đầy đủ List<Order> chỉ từ một đối tượng danh sách thông thường.

Trong trường hợp này, hãy truyền ResolvableType tường minh. Ví dụ, mô tả kiểu List<Order> có thể được tạo như sau:

~~~java
ResolvableType orderListType =
    ResolvableType.forClassWithGenerics(List.class, Order.class);
~~~

Event có thể lưu metadata payloadType được truyền vào constructor:

~~~java
public final class GenericPayloadEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T payload;
    private final ResolvableType payloadType;

    public GenericPayloadEvent(
            Object source,
            T payload,
            ResolvableType payloadType) {
        super(source);
        this.payload = payload;
        this.payloadType = payloadType;
    }

    public T getPayload() {
        return payload;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
            getClass(),
            payloadType
        );
    }
}
~~~

Khi phát event, truyền cả dữ liệu lẫn metadata:

~~~java
ResolvableType orderListType =
    ResolvableType.forClassWithGenerics(List.class, Order.class);

publisher.publishEvent(
    new GenericPayloadEvent<>(
        this,
        orders,
        orderListType
    )
);
~~~

Nhờ đó, kiểu event được mô tả là GenericPayloadEvent<List<Order>>. Listener có thể khai báo GenericPayloadEvent<List<Order>> nếu cần nhận đúng payload có cấu trúc này.

Metadata tường minh cũng hữu ích khi payload có thể null hoặc khi kiểu khai báo nghiệp vụ quan trọng hơn lớp triển khai runtime. Cần bảo đảm metadata phản ánh đúng payload được truyền vào.

## 8. Generic event và điều kiện SpEL là hai cơ chế khác nhau

Generic type dùng để phân biệt kiểu dữ liệu của event ở mức hợp đồng. Ví dụ, EntityCreatedEvent<Person> và EntityCreatedEvent<Organization> biểu diễn hai kiểu payload khác nhau.

Ngược lại, thuộc tính condition của @EventListener dùng biểu thức SpEL để lọc theo giá trị hoặc trạng thái của event:

~~~java
@EventListener(condition = "#event.entity.id() > 100")
public void handleLargeId(EntityCreatedEvent<Person> event) {
    // Chỉ xử lý Person có id lớn hơn 100.
}
~~~

Hai cơ chế có thể kết hợp:

- Tham số EntityCreatedEvent<Person> giới hạn listener ở biến thể Person.
- condition lọc tiếp theo giá trị của Person, ví dụ ID hoặc trạng thái.

Không nên dùng condition để thay thế generic type nếu điều kiện thực chất là phân biệt kiểu payload. Khai báo kiểu ở chữ ký phương thức dễ đọc hơn và giúp trình biên dịch kiểm tra kiểu.

## 9. Lưu ý khi thiết kế và sử dụng

**Không nhầm kiểu compile-time với kiểu runtime.** Java có thể suy luận EntityCreatedEvent<Person> khi biên dịch, nhưng instance không tự giữ lại toàn bộ tham số generic. Nếu cần Spring định tuyến theo tham số đó, event phải cung cấp metadata.

**Không chỉ dựa vào getClass().** getClass() trả về lớp runtime của object. Với một lớp generic, nó không cho biết T. Hãy dùng ResolvableTypeProvider để cung cấp cả lớp event và tham số generic.

**Chú ý kiểu payload là kiểu runtime.** ResolvableType.forInstance(entity) suy ra lớp thực tế của object. Nếu nghiệp vụ cần biểu diễn một kiểu interface, kiểu cha hoặc kiểu generic lồng nhau cụ thể, hãy cân nhắc truyền ResolvableType tường minh để tránh metadata khác với ý định thiết kế.

**Không giả định generic có tính covariance.** Trong Java, các kiểu như List<Dog> và List<Animal> không tự động thay thế cho nhau. Khi khai báo listener, hãy dùng tham số generic phù hợp chính xác với hợp đồng event và kiểm tra hành vi so khớp kiểu mong muốn.

**Giữ payload và metadata nhất quán.** Nếu event khai báo payloadType là List<Order> nhưng payload thực tế lại chứa loại dữ liệu khác, listener có thể hiểu sai dữ liệu. Metadata kiểu không thay thế việc xác thực đầu vào.

**Tránh dùng generic method để tạo bộ lọc runtime.** Một phương thức @EventListener có tham số kiểu T chưa được phân giải thường không giúp Spring phân biệt từng kiểu payload cụ thể. Khi cần định tuyến theo Person hoặc Organization, hãy khai báo listener với kiểu generic cụ thể.

**Không nhầm generic routing với async hoặc transaction.** ResolvableType chỉ hỗ trợ nhận diện kiểu event. Nó không quyết định listener chạy đồng bộ hay bất đồng bộ, không thay đổi thời điểm commit và không cung cấp bảo đảm giao nhận. Những yêu cầu đó cần được cấu hình riêng.

## 10. Cách kiểm tra generic event hoạt động đúng

Khi kiểm tra trong ứng dụng Spring, hãy tạo hai listener có kiểu tham số khác nhau và phát hai biến thể event:

1. Phát EntityCreatedEvent<Person> và xác nhận PersonCreatedListener được gọi.
2. Xác nhận OrganizationCreatedListener không xử lý event Person.
3. Phát EntityCreatedEvent<Organization> và xác nhận kết quả ngược lại.
4. Xác nhận listener dùng EntityCreatedEvent<?> nhận cả hai biến thể nếu đó là hành vi mong muốn.
5. Nếu payload có generic lồng nhau, kiểm tra ResolvableType được tạo từ metadata tường minh.

Nếu cả hai listener cụ thể đều nhận mọi event, hãy kiểm tra getResolvableType() của event có trả về đúng tham số generic hay không. Nếu không listener nào được gọi, kiểm tra chữ ký phương thức, loại event được publish và metadata có khớp kiểu mà listener khai báo hay không.

**Ghi nhớ:** generic event giúp tái sử dụng một hợp đồng sự kiện cho nhiều kiểu payload. Java type erasure khiến event cần cung cấp metadata runtime; Spring dùng ResolvableType và ResolvableTypeProvider để so khớp metadata đó với tham số generic của listener.