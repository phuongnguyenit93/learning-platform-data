# Tách dữ liệu và hành vi khi cần

**Chủ đề:** Thiết kế domain model trong Java Core Pattern Matching. Ví dụ chính sử dụng **Java 21+** với **sealed interface**, **record patterns** và **pattern matching for switch**. Đây là những tính năng chính thức của Java 21; không cần bật preview.

## 1. Vấn đề thiết kế: dữ liệu nên mang theo bao nhiêu hành vi?

Trong một domain model, **dữ liệu** biểu diễn sự thật, trạng thái, giá trị hoặc sự kiện của nghiệp vụ; **hành vi** biểu diễn quy tắc hoặc thao tác liên quan đến các dữ liệu ấy. Ví dụ, một sự kiện đặt hàng có mã đơn và tên khách hàng, trong khi các công việc như tạo dòng audit, gửi email, xuất báo cáo hay hiển thị trên giao diện có thể đều đọc cùng sự kiện nhưng phục vụ mục đích khác nhau.

Một cách thiết kế truyền thống là đưa các phương thức xử lý vào chính đối tượng:

~~~java
// Phác thảo thiết kế: không phải chương trình độc lập.
interface OrderEvent {
    String auditLine();
    String notificationText();
}
~~~

Cách này có lợi khi hành vi là một phần thiết yếu của khái niệm miền. Tuy nhiên, nếu mỗi lần thêm một loại báo cáo hay định dạng đầu ra lại phải sửa mọi subtype, các lớp domain dần phụ thuộc vào nhiều mối quan tâm không cùng trách nhiệm. Một mô hình khác là giữ các sự kiện mang **dữ liệu có cấu trúc** và đặt các cách diễn giải chúng ở những bộ xử lý riêng.

**Điểm cốt lõi:** không có nguyên tắc rằng mọi object domain đều phải “chỉ chứa dữ liệu”. Hãy tách khi hành vi thuộc trách nhiệm của một consumer, một quy trình hoặc một tầng hạ tầng khác; giữ hành vi trong domain khi chính đối tượng cần bảo vệ bất biến hay thực thi quy tắc nghiệp vụ cốt lõi.

## 2. Tận dụng sealed type và record để mô hình hóa các biến thể dữ liệu

Giả sử hệ thống có ba sự kiện của đơn hàng:

- **Placed:** đơn vừa được đặt; có mã đơn và tên khách.
- **Shipped:** đơn đã được gửi; có mã đơn và đơn vị vận chuyển.
- **Cancelled:** đơn đã hủy; có mã đơn và lý do.

Chúng khác cấu trúc dữ liệu nhưng đều là một loại **OrderEvent**. Trong Java 21, có thể biểu diễn bằng sealed interface và record:

~~~java
sealed interface OrderEvent permits Placed, Shipped, Cancelled {
    long orderId();
}

record Placed(long orderId, String customer) implements OrderEvent {}
record Shipped(long orderId, String carrier) implements OrderEvent {}
record Cancelled(long orderId, String reason) implements OrderEvent {}
~~~

Đoạn trên chỉ minh họa cách khai báo kiểu. Bản chương trình hoàn chỉnh ở mục 5 còn có bước kiểm tra dữ liệu đầu vào.

**Vì sao chọn cấu trúc này?**

1. **OrderEvent** thể hiện một tập hợp biến thể đóng: chỉ các subtype trực tiếp trong **permits** được phép triển khai.
2. Mỗi **record** công bố component của một giá trị, đồng thời có constructor, accessor, **equals**, **hashCode** và **toString** theo đặc tính record.
3. Record là final; kiểu sự kiện được biểu diễn như một giá trị đã ghi nhận thay vì một đối tượng cần mở rộng qua kế thừa.
4. Các bộ xử lý có thể dùng **switch** và record pattern để lấy thành phần tương ứng, đồng thời trình biên dịch kiểm tra khả năng bao phủ các loại sự kiện.

Tính sealed chỉ giới hạn **các subtype trực tiếp**. Nếu một nhánh permitted được khai báo **non-sealed**, các lớp con bên dưới nhánh ấy có thể tiếp tục mở rộng. Trong ví dụ, cả ba subtype là record (ngầm final), nên mỗi nhánh kết thúc ở đó.

### Record có thực sự bất biến không?

Record có các trường component dạng final, nhưng **không mặc nhiên bất biến sâu**. Nếu một component tham chiếu tới **List** hay một object có thể thay đổi, nội dung object đó vẫn có thể bị sửa qua tham chiếu. Ví dụ dùng String và long nên bản thân các component ở đây thuận tiện cho dữ liệu giá trị ổn định.

Với collection, một constructor có thể dùng **List.copyOf(...)** hoặc sao chép dữ liệu phù hợp; cần xét trường hợp phần tử bên trong còn mutable. Bất biến sâu là một quyết định thiết kế, không phải bảo đảm tự động của record.

## 3. Tách dữ liệu không có nghĩa bỏ validation và invariant

Một lỗi khi áp dụng mô hình “data + functions” là chuyển cả các quy tắc bảo vệ trạng thái ra ngoài record, khiến ở bất cứ đâu cũng có thể tạo sự kiện vô nghĩa:

~~~java
// Nếu không kiểm tra, có thể tạo dữ liệu không hợp lệ.
new Placed(0, "");
~~~

Đối với quy tắc cốt lõi như **orderId > 0** và **customer không null/không blank**, nên bảo đảm tại điểm tạo giá trị. Record có **compact constructor** để xác nhận các điều kiện đó.

~~~java
record Placed(long orderId, String customer) implements OrderEvent {
    Placed {
        checkId(orderId);
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("customer");
        }
    }
}
~~~

Đây là một đoạn trích; phương thức checkId và toàn bộ kiểu được định nghĩa trong chương trình mục 5. Các biến tham số của compact constructor được tự động gán cho component sau khi hoàn tất phần kiểm tra, nếu không có ngoại lệ.

Như vậy, **dữ liệu và bất biến về tính hợp lệ của nó** nằm cùng nơi. Các hành vi như **định dạng audit**, **quyết định thông báo**, **chuyển đổi DTO** hoặc **ghi vào hạ tầng** có thể được tách khỏi cấu trúc dữ liệu.

Cần phân biệt:

| Trách nhiệm | Nơi đặt thường phù hợp | Vì sao |
| --- | --- | --- |
| Giá trị bắt buộc, miền giá trị hợp lệ, bất biến của value object | Constructor hoặc phương thức domain | Bảo vệ dữ liệu ngay tại điểm tạo/thay đổi |
| Quy tắc quyết định thay đổi trạng thái aggregate | Aggregate hoặc domain service thích hợp | Bảo vệ tính nhất quán nghiệp vụ |
| Tạo dòng audit hoặc read model từ một event | Projector/formatter riêng | Là góc nhìn của một consumer |
| Quyết định nội dung email, push notification | Notification policy/service | Không buộc event biết về kênh gửi |
| Gọi cơ sở dữ liệu, HTTP hoặc gửi mail thực tế | Adapter/infrastructure service | Tránh trộn tác dụng phụ hạ tầng vào value object |
| Chuyển sự kiện sang JSON/DTO bên ngoài | Mapper/serializer boundary | Giảm sự phụ thuộc của domain vào định dạng vận chuyển |

Không nên chuyển mọi quy tắc nghiệp vụ ra khỏi object rồi gọi đó là tách trách nhiệm. Điều quan trọng là **quy tắc thuộc chủ thể nào và cần bảo vệ ở ranh giới nào**.

## 4. Pattern matching giúp đặt hành vi theo từng consumer

Khi các biến thể thuộc một **sealed hierarchy**, bộ xử lý có thể viết một **switch expression** trên kiểu cha:

~~~java
// Đoạn trích minh họa, giả sử các record đã khai báo.
static String auditLine(OrderEvent event) {
    return switch (event) {
        case Placed(long id, String customer) ->
                "AUDIT: " + id + " placed by " + customer;
        case Shipped(long id, String carrier) ->
                "AUDIT: " + id + " shipped via " + carrier;
        case Cancelled(long id, String reason) ->
                "AUDIT: " + id + " cancelled: " + reason;
    };
}
~~~

**Record pattern** như **Placed(long id, String customer)** kiểm tra kiểu record và trích hai component theo thứ tự khai báo. Nhánh switch không cần cast thủ công. Vì switch expression bao phủ cả ba biến thể của sealed OrderEvent, nó có thể **không có default** và vẫn exhaustive đối với các giá trị OrderEvent không null.

Từ một dữ liệu, consumer khác có thể tạo phản ứng khác, không làm record biết về nhu cầu consumer:

~~~java
static String notification(OrderEvent event) {
    return switch (event) {
        case Placed(long id, var customer) ->
                "EMAIL: receipt for " + id;
        case Shipped(long id, var carrier) ->
                "EMAIL: shipping update for " + id + " via " + carrier;
        case Cancelled(var id, var reason) -> "NO EMAIL";
    };
}
~~~

Hai phương thức **auditLine** và **notification** là hai **hành vi riêng** nhưng dùng chung kiểu dữ liệu. Cách này minh họa ý tưởng tách dữ liệu khỏi những **cách sử dụng dữ liệu**. Trong hệ thống thực tế, chúng có thể nằm trong hai service khác nhau với kiểm thử, phụ thuộc và tiến trình phát triển riêng.

**Lợi ích trực tiếp của sealed + switch:** nếu thêm event **Returned**, sau khi bổ sung subtype permitted, các switch expression không có default chưa có nhánh Returned sẽ bị compiler phát hiện thiếu trường hợp khi biên dịch lại. Những consumer cần quyết định cách xử lý event mới sẽ phải được rà soát.

**Đánh đổi:** cùng một hierarchy có thể xuất hiện ở nhiều switch khác nhau. Nếu một subtype mới thường xuyên được thêm, việc sửa nhiều consumer có thể tốn công. Đây chính là một tiêu chí quan trọng để quyết định có nên đặt hành vi vào từng subtype hay không.

## 5. Chương trình Java 21 hoàn chỉnh và có thể chạy

Lưu mã sau vào tệp **DataBehaviorSeparationDemo.java**. Ví dụ vừa giữ invariant trong record, vừa đặt hai cách đọc sự kiện ở các phương thức riêng. Đây là mô hình tối giản: **notification** chỉ *tạo nội dung giả lập*, không gửi email thật.

~~~java
import java.util.List;
import java.util.Objects;

public class DataBehaviorSeparationDemo {
    sealed interface OrderEvent permits Placed, Shipped, Cancelled {
        long orderId();
    }

    record Placed(long orderId, String customer) implements OrderEvent {
        Placed {
            checkId(orderId);
            if (customer == null || customer.isBlank()) {
                throw new IllegalArgumentException("customer");
            }
        }
    }

    record Shipped(long orderId, String carrier) implements OrderEvent {
        Shipped {
            checkId(orderId);
            if (carrier == null || carrier.isBlank()) {
                throw new IllegalArgumentException("carrier");
            }
        }
    }

    record Cancelled(long orderId, String reason) implements OrderEvent {
        Cancelled {
            checkId(orderId);
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("reason");
            }
        }
    }

    private static void checkId(long id) {
        if (id <= 0) throw new IllegalArgumentException("orderId");
    }

    static String auditLine(OrderEvent event) {
        Objects.requireNonNull(event, "event");
        return switch (event) {
            case Placed(long id, String customer) ->
                    "AUDIT: " + id + " placed by " + customer;
            case Shipped(long id, String carrier) ->
                    "AUDIT: " + id + " shipped via " + carrier;
            case Cancelled(long id, String reason) ->
                    "AUDIT: " + id + " cancelled: " + reason;
        };
    }

    static String notification(OrderEvent event) {
        Objects.requireNonNull(event, "event");
        return switch (event) {
            case Placed(long id, var customer) ->
                    "EMAIL: receipt for " + id;
            case Shipped(long id, var carrier) ->
                    "EMAIL: shipping update for " + id + " via " + carrier;
            case Cancelled(var id, var reason) -> "NO EMAIL";
        };
    }

    public static void main(String[] args) {
        List<OrderEvent> events = List.of(
                new Placed(101, "An"),
                new Shipped(101, "DHL"),
                new Cancelled(102, "duplicate"));

        for (OrderEvent event : events) {
            System.out.println(auditLine(event));
            System.out.println(notification(event));
        }

        try {
            new Placed(0, "An");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        try {
            auditLine(null);
        } catch (NullPointerException ex) {
            System.out.println("NULL REJECTED");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

~~~bash
javac DataBehaviorSeparationDemo.java
java DataBehaviorSeparationDemo
~~~

Đầu ra chính xác:

~~~text
AUDIT: 101 placed by An
EMAIL: receipt for 101
AUDIT: 101 shipped via DHL
EMAIL: shipping update for 101 via DHL
AUDIT: 102 cancelled: duplicate
NO EMAIL
INVALID: orderId
NULL REJECTED
~~~

**Phân tích kết quả:**

1. Dữ liệu đầu vào gồm ba sự kiện hợp lệ; trong mỗi lượt, **auditLine** và **notification** diễn giải cùng một event theo mục đích riêng.
2. **Cancelled** vẫn ghi audit nhưng không tạo thông báo email; không cần thêm phương thức email vào record Cancelled để đạt điều đó.
3. **new Placed(0, "An")** không hợp lệ, bị compact constructor từ chối với IllegalArgumentException. Như vậy việc tách xử lý bên ngoài không làm mất bất biến domain.
4. Cả hai phương thức xử lý dùng **Objects.requireNonNull(event, "event")**, quy định rõ rằng selector null bị từ chối. Thử auditLine(null) ném NullPointerException và được main bắt để in **NULL REJECTED**.
5. Các switch không dùng default vì ba subtype đã được bao phủ. Thêm subtype mới mà không cập nhật các switch sẽ dẫn đến lỗi biên dịch khi biên dịch lại mô hình và consumer.

Mã ví dụ đặt các kiểu và bộ xử lý trong cùng một class để dễ sao chép, chạy thử. Trong ứng dụng thực tế, việc tách thành **domain model**, **application service**, **read-model projector** và **infrastructure adapter** là một quyết định tổ chức mã riêng, không bắt buộc để pattern matching hoạt động.

## 6. Tiêu chí: khi nào nên tách và khi nào nên giữ hành vi trong kiểu?

Câu hỏi quan trọng là **thứ gì thay đổi thường xuyên hơn: các biến thể dữ liệu hay các thao tác áp dụng cho chúng?**

| Tình huống | Thiết kế thường đáng cân nhắc | Lý do |
| --- | --- | --- |
| Tập subtype tương đối ổn định, thường thêm báo cáo/quy trình xử lý | Sealed + record + switch theo consumer | Dễ thêm phép biến đổi mới mà không sửa các record |
| Cần nhiều cách hiển thị cùng một event | Tách formatter/projector ra ngoài | Domain event không phụ thuộc UI hoặc định dạng xuất |
| Hành vi chỉ thuộc một subtype và gắn chặt với bất biến của nó | Phương thức nằm ngay trong subtype | Giữ logic và trạng thái liên quan gần nhau |
| Thường bổ sung subtype mới, các thao tác tương đối ổn định | Polymorphism/virtual dispatch có thể tốt hơn | Thêm subtype cùng cách triển khai hành vi của nó |
| Logic quyết định thay đổi trạng thái entity/aggregate | Domain method hoặc domain service | Bảo vệ ranh giới nhất quán, tránh anemic domain |
| Hành vi phụ thuộc email, database, API ngoài | Application/infrastructure service | Tách side effects và phụ thuộc kỹ thuật |
| Kiểu dữ liệu là DTO hay event bất biến | Record là ứng viên phù hợp | Chủ yếu truyền giá trị, dễ so sánh và deconstruction |
| Entity có danh tính, vòng đời, trạng thái chuyển tiếp và ORM phức tạp | Class/aggregate phù hợp hơn record thuần | Record không tự giải quyết identity và lifecycle |

**Không có lựa chọn nào luôn tốt hơn.** Sealed + pattern switch thiên về thiết kế dễ **thêm thao tác mới**; đặt hành vi polymorphic vào từng subtype thiên về thiết kế dễ **thêm kiểu mới** cho một tập hành vi sẵn có. Cả hai đều có chi phí mở rộng, và một hệ thống có thể sử dụng cả hai ở các ranh giới khác nhau.

## 7. So sánh với thiết kế polymorphism

Giả sử giao diện OrderEvent yêu cầu chính event biết tạo dòng audit:

~~~java
// Phác thảo phương án polymorphism, KHÔNG ghép vào chương trình mục 5.
interface Auditable {
    String auditLine();
}

record Placed(long orderId, String customer) implements Auditable {
    @Override
    public String auditLine() {
        return "AUDIT: " + orderId + " placed by " + customer;
    }
}
~~~

Ở phương án này, một client có thể gọi **event.auditLine()** qua interface. Thêm subtype mới sẽ phải cài đặt auditLine() nếu interface bắt buộc. Nhưng nếu cần thêm nhiều thao tác hoàn toàn mới như **notificationText()**, **searchIndexDocument()**, **exportCsv()**, việc thêm method vào interface kéo theo chỉnh sửa nhiều subtype hoặc các lớp adapter.

Trong cách dùng pattern matching, mỗi bộ xử lý có các nhánh case riêng theo subtype. Thêm một thao tác không cần sửa record; thêm subtype buộc sửa các switch có yêu cầu xử lý nó.

Hai hướng này thường được mô tả bằng lựa chọn mở rộng theo **hàng (thêm kiểu dữ liệu)** hay **cột (thêm thao tác)**. Đừng quyết định chỉ vì số dòng ít hơn: hãy so với nhịp thay đổi thực tế của domain và nơi logic được sở hữu.

## 8. Tránh biến domain thành “anemic model”

**Anemic domain model** là trường hợp object chỉ giữ dữ liệu còn gần như mọi quy tắc nghiệp vụ quan trọng bị đẩy ra những service ngoài, làm các bất biến và quá trình thay đổi trạng thái khó kiểm soát. Tách định dạng audit khỏi event không tự động tạo ra vấn đề này.

Ranh giới cần rõ:

- **Event:** biểu diễn một sự thật đã xảy ra (ví dụ đơn đã được gửi), thường được tạo bởi logic nghiệp vụ khác. Event có thể giữ validation và dữ liệu ổn định.
- **Command:** mô tả yêu cầu thực hiện một hành động, có thể cần service/aggregate xác thực trước khi chấp nhận.
- **Entity/Aggregate:** quản lý danh tính, vòng đời và quy tắc thay đổi trạng thái. Những phương thức như **ship()** có thể phải nằm tại aggregate hoặc domain service, không nên chỉ được thực thi bằng các switch rải khắp hệ thống.
- **Projection/Notification:** đọc event để tạo góc nhìn hoặc tác dụng phụ bên ngoài. Đây là nơi tách hành vi thường hợp lý.

Ví dụ, quy tắc **không được giao hàng khi đơn đã hủy** không phải chi tiết trình bày. Nó cần được bảo vệ tại nơi thực thi lệnh chuyển trạng thái, thường ở aggregate hoặc domain service phù hợp. Đừng để các formatter quyết định tính hợp lệ của trạng thái domain.

Ngược lại, thông điệp “shipping update for 101 via DHL” là kết quả phục vụ một consumer; đặt nó trong notification service thường giúp domain không phụ thuộc cách diễn đạt và kênh gửi.

## 9. Giới hạn và rủi ro khi dùng pattern matching để tách hành vi

### 9.1. Một subtype mới ảnh hưởng nhiều consumer

Sealed hierarchy giúp compiler phát hiện những switch không exhaustive khi thêm subtype mới. Đó là ưu điểm kiểm soát thay đổi, nhưng cũng có thể tạo nhiều vị trí cần cập nhật. Nếu một subtype thường xuyên được thêm và luôn mang cùng hành vi trừu tượng, polymorphism có thể giảm việc sửa nhiều bộ xử lý.

Nếu vẫn chọn switch, nên **gom mỗi trách nhiệm về một service**. Không nên đặt một switch giống nhau ở controller, repository, scheduler và mapper rồi để chúng độc lập phát triển.

### 9.2. Rò rỉ kiểu cụ thể ra toàn bộ hệ thống

Khi mọi lớp đều biết Placed, Shipped và Cancelled, mã phụ thuộc chặt vào danh sách subtype. Có thể dùng mapper/projector tại một boundary để chuyển thành một giao diện hoặc DTO ổn định hơn cho tầng tiêu thụ.

Pattern matching hiệu quả khi một thành phần **có lý do để hiểu mọi biến thể**. Nó không có nghĩa mọi thành phần đều nên làm như vậy.

### 9.3. Case dài và mẫu lồng sâu

Một case có record pattern ba, bốn cấp và nhiều **when** có thể khó đọc hơn lời gọi phương thức. Nếu cần kiểm tra quy tắc phức tạp, hãy tách ra một phương thức đặt tên theo nghiệp vụ. Giữ switch ở vai trò **chọn nhánh theo hình dạng dữ liệu**, không biến nó thành một chương trình dài bên trong case.

### 9.4. Nhầm tính exhaustive với tính hợp lệ

Compiler có thể chứng minh switch bao phủ đủ subtype; nó **không chứng minh** customer không blank, orderId dương hay lệnh gửi email an toàn. Validation và invariant vẫn cần đặt ở nơi thích hợp. Trình biên dịch cũng không tự suy luận rằng các guard bất kỳ như **when x > 0** và **when x <= 0** đủ bao phủ mọi giá trị: thường cần case tổng quát tương ứng.

### 9.5. Null và kiểu tham chiếu

Một switch trên sealed hierarchy có thể exhaustive cho mọi giá trị không null nhưng vẫn từ chối null. Trong ví dụ, **Objects.requireNonNull** xác định chính sách từ chối đầu vào null. Nếu null có ý nghĩa nghiệp vụ, có thể thiết kế **case null** với hành vi phù hợp thay vì để lỗi bất ngờ.

Với record pattern lồng nhau, nếu component record con là null thì mẫu lồng cụ thể không khớp. Với component tham chiếu được ràng buộc bằng **var** trong record pattern, biến có thể chứa null nếu constructor record cho phép. Không đồng nhất “khớp pattern” với “mọi component đều khác null”.

### 9.6. Tác dụng phụ và tính thuần túy

Một bộ xử lý dùng switch chỉ để tạo String là ví dụ **pure transformation** dễ kiểm thử. Nếu case phải gửi email, ghi DB hoặc gọi dịch vụ ngoài, nên cân nhắc tách phần **quyết định** khỏi phần **thực thi tác dụng phụ**, để dễ retry, quan sát lỗi và bảo vệ tính nhất quán.

Không nên xây dựng hành vi quan trọng dựa trên giả định accessor của mọi record đều thuần túy: Java cho phép viết accessor tường minh, nên việc giải cấu trúc có thể kích hoạt logic trong accessor nếu kiểu được thiết kế như vậy.

## 10. Quy trình refactor có thể áp dụng

Khi đang có một hierarchy với dữ liệu và nhiều hành vi trộn lẫn, hãy thực hiện theo các bước:

1. **Phân loại trách nhiệm:** xác định invariant, quy tắc trạng thái, định dạng, tích hợp và những xử lý dành riêng cho consumer.
2. **Xác định miền biến thể:** kiểu nào có thể thay đổi, kiểu nào có thể biểu diễn bằng sealed interface và immutable record? Không chuyển entity mutable sang record một cách cơ học.
3. **Giữ invariant tại ranh giới tạo/sửa dữ liệu:** bổ sung validation cho các điều kiện có thể thực sự bảo đảm tại đây.
4. **Tách từng consumer:** chuyển riêng một thao tác như audit formatting sang một hàm/service dùng switch, thay vì thay đổi tất cả cùng lúc.
5. **Đối chiếu hành vi:** thêm test cho từng subtype, null, dữ liệu không hợp lệ và case mới; kiểm tra cả exceptions, logging, thứ tự side effects.
6. **Đánh giá số nơi biết subtype:** nếu pattern switch tràn lan và lặp logic, thiết kế lại boundary hoặc quay về polymorphism cho trách nhiệm chung.
7. **Kiểm tra khả năng mở rộng:** thử bổ sung subtype mới và quan sát compiler nhắc ở các switch cần xử lý; sửa với quyết định nghiệp vụ rõ ràng.
8. **Không lạm dụng default:** trên sealed hierarchy, default có thể che việc thiếu case khi mở rộng. Chỉ dùng nếu một hành vi dự phòng chung thật sự được định nghĩa.

## 11. Checklist code review

| Câu hỏi | Tín hiệu thiết kế tốt |
| --- | --- |
| Dữ liệu nào là sự kiện/giá trị, dữ liệu nào là entity có vòng đời? | Kiểu được chọn dựa trên ngữ nghĩa, không phải cú pháp ngắn |
| Có invariant nào buộc phải đúng khi tạo hoặc thay đổi object? | Được bảo vệ ở constructor/aggregate/domain service |
| Các consumer có lý do riêng để diễn giải dữ liệu? | Formatter, projector, notification được tách rõ |
| Tập subtype có đóng và được quản lý không? | Sealed/record phù hợp, các switch exhaustive khi cần |
| Thêm một thao tác mới có làm sửa hàng loạt subtype không? | Cân nhắc tách hành vi bên ngoài |
| Thêm subtype mới có làm sửa rất nhiều switch không? | Cân nhắc polymorphism hoặc boundary ổn định |
| Có logic hoặc side effect bị sao chép ở nhiều switch không? | Gom trách nhiệm hoặc chuyển vào service/phương thức phù hợp |
| Các trường hợp null, sai dữ liệu, sai loại đã được kiểm thử chưa? | Kiểm thử đầy đủ, không dựa riêng vào exhaustiveness |

**Kết luận:** Tách dữ liệu và hành vi **khi trách nhiệm thực sự khác nhau** giúp domain model gọn, consumer có thể phát triển độc lập, và sealed + record patterns hỗ trợ phân nhánh an toàn kiểu. Nhưng những quy tắc tạo giá trị hợp lệ và giữ trạng thái miền nhất quán vẫn phải được bảo vệ ở đúng chủ thể. Hãy chọn giữa **pattern switch bên ngoài** và **polymorphism bên trong** dựa trên hướng thay đổi của hệ thống, thay vì coi “data-only object” là mục tiêu tuyệt đối.