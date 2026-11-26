# Kiểm soát phụ thuộc trực tiếp, phụ thuộc bắc cầu và chu trình giữa các tầng

Trong kiến trúc phân tầng, việc chia mã nguồn thành các nhóm như trình bày, ứng dụng, miền nghiệp vụ và truy cập dữ liệu chỉ tạo ra giá trị khi các nhóm có ranh giới rõ ràng. Ranh giới đó được thể hiện qua những phụ thuộc mà mỗi tầng được phép tạo ra. Nếu một tầng tùy ý gọi hoặc tham chiếu mọi tầng khác, cấu trúc ban đầu sẽ dần mất ý nghĩa: thay đổi ở một nơi lan rộng, kiểm thử khó cô lập và việc thay thế một thành phần trở nên tốn kém.

Bài học này tập trung vào cách đọc và kiểm soát đồ thị phụ thuộc: nhận biết cạnh phụ thuộc trực tiếp, hiểu đường phụ thuộc bắc cầu, phát hiện chu trình và chọn cách tháo gỡ phù hợp. Ví dụ dùng Java và Spring để minh họa, nhưng các nguyên tắc áp dụng cho những hệ thống phân tầng khác. Số lượng tầng và cách đặt tên tầng có thể thay đổi theo hệ thống; điều cần xác định là trách nhiệm, hợp đồng và hướng phụ thuộc của từng ranh giới.

## 1. Đọc đồ thị phụ thuộc đúng cách

Một thành phần **phụ thuộc trực tiếp** vào thành phần khác khi mã nguồn hoặc cấu hình của nó cần biết thành phần kia để biên dịch, cấu hình hay thực hiện trách nhiệm của mình. Trong Java, dấu hiệu thường gặp là tham chiếu kiểu trong khai báo trường, tham số, kiểu trả về, kế thừa, triển khai interface, annotation hoặc lời gọi phương thức. Việc dùng tên đầy đủ thay cho câu lệnh import không làm mất đi phụ thuộc đó.

Khi vẽ đồ thị, quy ước mũi tên A → B có nghĩa là **A phụ thuộc vào B**. Mũi tên đi từ bên sử dụng đến bên được sử dụng. Quy ước này giúp tránh nhầm lẫn giữa hướng phụ thuộc trong mã nguồn và thứ tự các thành phần được gọi khi chương trình chạy.

Ví dụ, một ứng dụng đặt hàng có thể tổ chức trách nhiệm thành các nhóm logic:

- **presentation:** nhận HTTP request, kiểm tra dữ liệu đầu vào ở mức giao tiếp và chuyển yêu cầu cho ứng dụng.
- **application:** điều phối ca sử dụng, quản lý giao dịch và gọi các cổng cần thiết.
- **domain:** giữ quy tắc và trạng thái nghiệp vụ như đơn hàng, dòng hàng và điều kiện chuyển trạng thái.
- **infrastructure.persistence:** hiện thực việc lưu trữ bằng JPA hoặc một công nghệ cụ thể.

Đây là các tầng logic trong ví dụ, không nhất thiết là bốn tiến trình hay bốn máy chủ riêng. Một ứng dụng Spring Boot có thể đóng gói tất cả trong một tiến trình mà vẫn giữ các ranh giới này.

Giả sử tầng ứng dụng khai báo cổng lưu đơn hàng OrderRepository, còn tầng hạ tầng cung cấp lớp hiện thực cổng đó:

~~~java
// application/port/OrderRepository.java
public interface OrderRepository {
    void save(Order order);
}

// application/PlaceOrderUseCase.java
public interface PlaceOrderUseCase {
    void place(PlaceOrderCommand command);
}

// application/PlaceOrderService.java
@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public void place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.items());
        orders.save(order);
    }
}

// infrastructure/persistence/JpaOrderRepository.java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    public JpaOrderRepository(SpringDataOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public void save(Order order) {
        jpa.save(OrderEntity.from(order));
    }
}
~~~

Trong thiết kế này, PlaceOrderService biết interface OrderRepository, không biết lớp JpaOrderRepository. Lớp adapter JPA biết interface để triển khai nó, đồng thời biết các kiểu cần thiết để ánh xạ sang mô hình lưu trữ. Đồ thị phụ thuộc mã nguồn có thể được mô tả như sau:

~~~mermaid
flowchart LR
    P["presentation"] --> A["application"]
    A --> D["domain"]
    I["infrastructure.persistence"] --> A
    I --> D
~~~

Khi xử lý một request, luồng gọi lúc chạy có thể đi từ controller đến PlaceOrderService, rồi qua interface OrderRepository đến đối tượng JpaOrderRepository do Spring cung cấp, sau đó mới đến cơ sở dữ liệu. Luồng gọi đó không đảo ngược đồ thị phụ thuộc mã nguồn. Mã nguồn của tầng ứng dụng vẫn chỉ tham chiếu interface thuộc ranh giới ứng dụng; adapter ở tầng hạ tầng mới phụ thuộc vào interface ấy.

Đây là điểm quan trọng khi dùng dependency injection: Spring có thể tạo và kết nối đối tượng cụ thể lúc chạy, nhưng việc tiêm một đối tượng qua constructor không xóa phụ thuộc kiểu trong mã nguồn. Nếu PlaceOrderService import JpaOrderRepository và khai báo trường bằng kiểu cụ thể đó, tầng ứng dụng đã phụ thuộc trực tiếp vào hạ tầng dù đối tượng vẫn được Spring khởi tạo.

## 2. Phân biệt phụ thuộc trực tiếp và phụ thuộc bắc cầu

Giả sử đồ thị có đường đi:

~~~text
presentation → application → domain
~~~

presentation phụ thuộc trực tiếp vào application. Vì application phụ thuộc vào domain, nên presentation có một **đường phụ thuộc bắc cầu** đến domain. Đường đi này cho biết thay đổi ở tầng miền có thể ảnh hưởng gián tiếp đến tầng trình bày thông qua tầng ứng dụng. Nó không tự động có nghĩa là mã nguồn trình bày được phép tham chiếu mọi kiểu trong miền.

Cần phân biệt ba tình huống:

1. **Có đường đi bắc cầu:** controller gọi một use case thuộc application, use case dùng domain. Nếu controller không tham chiếu kiểu miền, controller chưa tạo cạnh mã nguồn trực tiếp đến domain.
2. **Hợp đồng làm lộ kiểu của tầng dưới:** nếu phương thức use case công khai trả về Order thuộc domain, controller phải biết kiểu Order để sử dụng kết quả. Khi đó có thêm phụ thuộc trực tiếp từ presentation đến domain, dù controller chỉ gọi một phương thức của application.
3. **Phụ thuộc được truyền qua công cụ build:** một thư viện hoặc module có thể xuất hiện trên classpath do dependency khác khai báo. Khả năng import được một kiểu nhờ classpath không đồng nghĩa kiến trúc cho phép tầng hiện tại sử dụng kiểu đó.

Do đó, khi đánh giá một phụ thuộc, hãy kiểm tra cả đồ thị module, tham chiếu trong mã nguồn và kiểu xuất hiện trong API công khai. Đừng chỉ nhìn vào việc dự án có biên dịch hay không. Classpath rộng có thể che giấu một cạnh phụ thuộc mà quy tắc kiến trúc không cho phép.

### 2.1. Quy tắc tầng đóng và tầng mở

Quy tắc tầng xác định những cạnh trực tiếp nào được chấp nhận:

- Với **tầng đóng** (closed layer), một tầng chỉ được truy cập tầng liền kề theo hướng đã quy định. Ví dụ, presentation gọi application, rồi application làm việc với domain. Tầng trình bày không được bỏ qua tầng ứng dụng để gọi thẳng tầng miền.
- Với **tầng mở** (open layer), một tầng có thể được phép bỏ qua một hoặc nhiều tầng trung gian trong những trường hợp đã xác định. Chẳng hạn, một luồng truy vấn đơn giản có thể được phép đọc một kiểu dữ liệu miền mà không cần đi qua toàn bộ chuỗi điều phối, nếu thiết kế chấp nhận và ghi rõ ngoại lệ đó.

Không có lựa chọn mở hay đóng nào đúng cho mọi hệ thống. Tầng đóng làm cho luồng điều phối nhất quán và giảm khả năng các tầng trên biết quá nhiều chi tiết bên dưới, nhưng đôi khi tạo thêm các phương thức chuyển tiếp ít giá trị. Tầng mở có thể giảm lớp trung gian, nhưng cần quy định cụ thể các đường truy cập được phép để không biến thành phụ thuộc tùy ý.

Một quy tắc thực tế cho ví dụ đặt hàng là: presentation chỉ truy cập hợp đồng ứng dụng; application sử dụng mô hình miền và các cổng do chính nó sở hữu; infrastructure hiện thực các cổng đó. Nếu một hệ thống chọn cho phép presentation truy cập trực tiếp một số kiểu miền, ngoại lệ cần được nêu rõ và kiểm soát bằng kiểm thử kiến trúc.

### 2.2. Nhận biết phụ thuộc bắc cầu nguy hiểm

Phụ thuộc bắc cầu trở thành vấn đề khi hợp đồng của tầng trung gian để lộ quá nhiều chi tiết của tầng dưới. Ví dụ, controller nhận trực tiếp OrderEntity của JPA hoặc use case trả về Page<OrderEntity>. Khi đó, cấu trúc lưu trữ đã đi xuyên qua ranh giới ứng dụng đến tầng trình bày. Đổi từ JPA sang một cách lưu trữ khác có thể buộc controller và các kiểm thử HTTP phải thay đổi.

Có thể giảm sự rò rỉ bằng cách:

- Dùng command, query result hoặc DTO phù hợp với hợp đồng của ca sử dụng ở ranh giới ứng dụng.
- Chuyển đổi OrderEntity sang mô hình miền hoặc kết quả ứng dụng bên trong adapter lưu trữ.
- Không để kiểu của framework persistence, chi tiết kết nối hay đối tượng HTTP xuất hiện trong API của tầng không sở hữu chúng.
- Khai báo rõ module nào được phép phụ thuộc module nào; tránh dựa vào dependency bắc cầu trên classpath như một cách chia sẻ kiểu ngầm định.

Không cần tạo DTO cho mọi kiểu dữ liệu một cách máy móc. Hãy tạo kiểu biên khi nó bảo vệ được một hợp đồng thực sự: định dạng API cần ổn định, mô hình lưu trữ có thể thay đổi độc lập, hoặc tầng gọi không nên biết quy tắc nội bộ của tầng được gọi.

## 3. Chu trình phụ thuộc giữa các tầng

Một đồ thị có **chu trình** khi bắt đầu từ một thành phần, đi theo các cạnh phụ thuộc và có thể quay lại chính thành phần đó. Với hai tầng A và B, chu trình thường có dạng A → B → A.

Ví dụ, tầng ứng dụng import lớp JpaOrderRepository để tự khởi tạo hoặc gọi trực tiếp nó, trong khi JpaOrderRepository triển khai OrderRepository được khai báo ở tầng ứng dụng:

~~~mermaid
flowchart LR
    A["application"] --> I["infrastructure.persistence"]
    I --> A
~~~

Tầng ứng dụng cần hạ tầng để làm việc, còn hạ tầng cần tầng ứng dụng để triển khai hợp đồng. Hai tầng đã khóa chặt vào nhau. Một ví dụ khác là domain import một service thuộc application trong khi service đó cũng dùng kiểu miền. Khi đó, quy tắc hướng phụ thuộc vào trong đã bị phá vỡ.

Chu trình có thể xuất hiện ở nhiều mức:

- **Mức lớp:** hai lớp tham chiếu lẫn nhau.
- **Mức package:** các package có đường phụ thuộc qua lại, dù không có một cặp lớp đơn giản nào thể hiện toàn bộ chu trình.
- **Mức module:** hai module build cần nhau. Với các module Maven riêng, chu trình dependency thường khiến reactor không thể xác định thứ tự build hợp lệ.
- **Mức đối tượng lúc chạy:** các bean Spring phụ thuộc constructor lẫn nhau có thể tạo vòng tham chiếu khi khởi tạo context.

Các mức này liên quan nhưng không đồng nhất. Một chu trình giữa package có thể biên dịch được nếu chúng cùng module Java, nhưng vẫn làm kiến trúc khó hiểu. Một lỗi circular dependency khi Spring tạo bean là dấu hiệu cần điều tra đồ thị đối tượng; nó không tự chứng minh rằng mọi package hoặc module cũng có chu trình. Ngược lại, hai package phụ thuộc mã nguồn lẫn nhau vẫn có thể không tạo ra vòng khởi tạo bean.

Đừng suy ra chu trình kiến trúc chỉ từ thứ tự gọi lúc chạy. Một service có thể gọi interface, adapter thực thi interface đó, và adapter có thể phát sự kiện để một thành phần khác xử lý. Luồng điều khiển có thể quay lại một thành phần trước đó trong một kịch bản nghiệp vụ mà đồ thị tham chiếu mã nguồn vẫn không có chu trình. Khi kiểm tra, hãy ghi rõ mình đang xem đồ thị tham chiếu mã nguồn, đồ thị module, đồ thị bean hay luồng gọi runtime.

### 3.1. Vì sao chu trình gây khó khăn?

Chu trình làm mờ quyền sở hữu trách nhiệm. Khi A và B cần biên dịch hoặc thay đổi cùng nhau, khó xác định thành phần nào cung cấp hợp đồng ổn định. Việc kiểm thử riêng một tầng cũng khó hơn vì phải dựng các thành phần còn lại theo một thứ tự hoặc cấu hình phức tạp. Khi tách module, triển khai độc lập hoặc thay thế adapter, chu trình có thể buộc phải kéo theo cả nhóm thành phần.

Ở mức mã nguồn, chu trình còn khiến thay đổi nhỏ lan truyền rộng. Ví dụ, nếu controller và repository cùng phụ thuộc trực tiếp vào entity JPA, một thay đổi mapping hoặc quan hệ entity có thể ảnh hưởng cả giao tiếp HTTP. Nếu tầng ứng dụng phụ thuộc lớp repository cụ thể, thay đổi constructor hoặc cách cấu hình repository có thể tác động đến logic nghiệp vụ.

## 4. Phát hiện và kiểm soát phụ thuộc

Có thể kiểm tra phụ thuộc theo một quy trình ngắn:

1. **Chọn mức cần kiểm soát.** Xác định quy tắc áp dụng cho module, package hay lớp. Không nên tuyên bố “các tầng không phụ thuộc nhau” nếu thực tế chỉ kiểm tra dependency giữa các module.
2. **Liệt kê các cạnh trực tiếp.** Kiểm tra tham chiếu kiểu, import, kế thừa, annotation, chữ ký phương thức công khai, cấu hình Spring và dependency được khai báo trong Maven hoặc Gradle.
3. **Lần theo các đường bắc cầu.** Với mỗi tầng, tìm xem có thể đi đến tầng nào khác qua một hay nhiều cạnh. Sau đó kiểm tra đường đi đó có làm lộ kiểu hoặc hợp đồng không phù hợp ở ranh giới trên hay không.
4. **Tìm đường quay về điểm xuất phát.** Nếu A đi đến B và B có đường quay lại A, đã có chu trình ở mức đồ thị đang xét. Với hệ thống lớn, có thể gom các package hoặc module nằm trong cùng nhóm liên thông mạnh để khoanh vùng.
5. **Đưa quy tắc vào kiểm thử.** Kiểm thử tự động giúp ngăn một import hoặc dependency mới vô tình phá vỡ ranh giới sau này.

Ví dụ dưới đây dùng ArchUnit để ngăn tầng miền tham chiếu các tầng bên ngoài. Tên package cần điều chỉnh theo cấu trúc dự án:

~~~java
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

@AnalyzeClasses(packages = "com.example.orders")
class LayerDependencyTest {

    @ArchTest
    static final ArchRule domainDoesNotDependOnOuterLayers =
        noClasses().that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..presentation..",
                "..application..",
                "..infrastructure.."
            );

    @ArchTest
    static final ArchRule applicationDoesNotDependOnInfrastructure =
        noClasses().that().resideInAPackage("..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("..infrastructure..");
}
~~~

Quy tắc thứ hai ngăn tầng ứng dụng tham chiếu trực tiếp hạ tầng. Trong khi đó, hạ tầng vẫn có thể phụ thuộc vào interface ở tầng ứng dụng để hiện thực cổng. Nếu hệ thống dùng tầng mở hoặc có ngoại lệ được chấp thuận, hãy biểu diễn ngoại lệ đó trong quy tắc và tài liệu kiến trúc thay vì âm thầm nới lỏng mọi package.

Kiểm thử kiến trúc không thay thế review thiết kế. Một rule có thể xác nhận rằng không có import từ domain sang infrastructure, nhưng không thể tự đánh giá một API có đang để lộ entity, schema hay khái niệm của framework qua ranh giới hay không. Cần kết hợp kiểm thử với việc đọc hợp đồng công khai và xem xét các đường phụ thuộc bắc cầu.

## 5. Cách tháo gỡ chu trình

Khi phát hiện chu trình, trước hết hãy xác định cạnh nào khiến hướng phụ thuộc bị đảo ngược. Không nên vội chuyển tất cả kiểu dùng chung vào một package common; cách đó thường chỉ che giấu sự phụ thuộc và tạo ra một nơi chứa nhiều khái niệm không cùng trách nhiệm.

Với ví dụ application ↔ infrastructure.persistence, cách sửa thường dùng là đặt interface tại ranh giới hướng vào mà bên điều phối sở hữu, rồi để adapter hạ tầng triển khai interface đó:

~~~mermaid
flowchart LR
    P["presentation"] --> A["application"]
    A --> R["OrderRepository port"]
    I["JpaOrderRepository adapter"] --> R
    A --> D["domain"]
    I --> D
~~~

Sau khi thay đổi:

- application gọi OrderRepository, là hợp đồng mô tả khả năng lưu đơn hàng mà ca sử dụng cần.
- infrastructure.persistence triển khai hợp đồng bằng JPA và chịu trách nhiệm chuyển đổi giữa entity lưu trữ với mô hình phù hợp.
- Spring kết nối implementation với interface qua cấu hình hoặc component scanning.
- application không cần biết tên lớp adapter, annotation repository hay API của Spring Data.

Nếu chu trình bắt nguồn từ kiểu dữ liệu bị đặt sai nơi, hãy chuyển quyền sở hữu kiểu về tầng phù hợp hoặc tạo một hợp đồng biên nhỏ hơn. Ví dụ, controller có thể nhận PlaceOrderRequest, chuyển thành PlaceOrderCommand, rồi trả PlaceOrderResponse; không cần trả OrderEntity ra ngoài. Nếu hai package thực sự cùng chịu trách nhiệm và luôn phải thay đổi cùng nhau, có thể xem xét tổ chức chúng trong cùng một module hoặc ranh giới hợp lý hơn thay vì cố giữ một đường phân tầng giả tạo.

Khi các thành phần cần thông báo cho nhau mà không nên tham chiếu trực tiếp, có thể dùng domain event, application event hoặc message contract. Hãy đặt hợp đồng ở nơi có quyền sở hữu rõ ràng, xác định ai phát và ai xử lý, đồng thời chấp nhận các đặc tính của giao tiếp bất đồng bộ nếu dùng message broker. Sự kiện không phải cách né mọi phụ thuộc: một event chứa entity JPA hoặc kiểu nội bộ của adapter vẫn làm rò rỉ chi tiết qua ranh giới.

Sau khi sửa, cập nhật kiểm thử kiến trúc và kiểm thử ca sử dụng liên quan. Xác nhận rằng tầng điều phối vẫn gọi được cổng cần thiết, adapter vẫn được Spring cấu hình đúng và dữ liệu được ánh xạ chính xác. Nếu tách module, kiểm tra lại dependency của build để bảo đảm module hướng vào không cần khai báo module hạ tầng.

## 6. Các tình huống thường gặp

| Tình huống | Cách đọc phụ thuộc | Hướng xử lý |
|---|---|---|
| Controller gọi PlaceOrderUseCase thuộc application | Cạnh trực tiếp presentation → application | Phù hợp với quy tắc tầng đóng trong ví dụ |
| Controller dùng Order trong chữ ký hoặc xử lý kết quả | Có cạnh trực tiếp đến domain, dù đã đi qua application | Dùng hợp đồng ứng dụng/DTO nếu quy tắc không cho phép bỏ tầng |
| Application gọi interface repository, adapter JPA triển khai interface | application sở hữu hợp đồng; infrastructure phụ thuộc vào hợp đồng | Giữ interface ở ranh giới phù hợp và inject implementation |
| Application import JpaOrderRepository | Cạnh trực tiếp application → infrastructure; có thể tạo chu trình nếu adapter cũng phụ thuộc application | Đảo phụ thuộc qua port/interface |
| Hai module khai báo dependency lẫn nhau | Chu trình ở mức module | Tách hợp đồng, đổi quyền sở hữu hoặc điều chỉnh ranh giới module |
| Runtime callback quay lại một thành phần trước đó | Có thể là vòng điều khiển lúc chạy, chưa chắc là chu trình tham chiếu mã nguồn | Kiểm tra riêng luồng gọi, đồ thị bean và đồ thị mã nguồn |

## 7. Cân bằng giữa kiểm soát và chi phí

Quy tắc phụ thuộc càng chặt thì ranh giới càng dễ kiểm tra, nhưng hệ thống cũng có thể cần thêm command, DTO, adapter hoặc bước ánh xạ. Những thành phần này có ích khi chúng bảo vệ hợp đồng và cho phép các phần thay đổi độc lập. Nếu chúng chỉ chuyển nguyên dữ liệu qua nhiều lớp mà không bảo vệ ranh giới nào, cần xem lại cách chia tầng.

Ngược lại, cho phép mọi tầng truy cập mọi tầng bên dưới có thể làm code ngắn hơn trong thời gian đầu, nhưng khiến một tầng phụ thuộc vào nhiều chi tiết hơn mức trách nhiệm của nó yêu cầu. Đặc biệt, việc để API công khai của tầng trung gian làm lộ kiểu persistence hoặc framework khiến chi phí thay đổi lan sang các tầng phía trên.

Khi chọn quy tắc, hãy dựa vào mục tiêu cụ thể: tầng nào cần thay đổi độc lập, hợp đồng nào cần ổn định, nhóm nào cần kiểm thử riêng và ngoại lệ bỏ qua tầng trung gian có lợi ích gì. Giữ đồ thị phụ thuộc ở mức ranh giới đã chọn không có chu trình; cho phép đường bắc cầu khi phù hợp với thiết kế, nhưng kiểm soát các cạnh trực tiếp và kiểu được lộ qua hợp đồng.

## 8. Tự kiểm tra trước khi thêm một phụ thuộc

Trước khi thêm một import hoặc dependency giữa hai tầng, hãy tự hỏi:

- Thành phần hiện tại cần biết hợp đồng nào để hoàn thành trách nhiệm của nó?
- Phụ thuộc mới là cạnh trực tiếp ở mức lớp, package hay module?
- Có thể đi từ tầng hiện tại qua các cạnh khác để đến một tầng không được phép truy cập không?
- Kiểu của framework, persistence hoặc giao tiếp bên ngoài có bị lộ qua API công khai không?
- Cạnh mới có tạo đường quay lại tầng xuất phát hay làm phát sinh chu trình không?
- Quy tắc này đã được thể hiện trong kiểm thử kiến trúc hoặc tài liệu ngoại lệ chưa?

Nếu câu trả lời cho thấy một tầng đang biết chi tiết triển khai của tầng khác, hãy xem xét thu hẹp hợp đồng, chuyển interface về phía cần khả năng đó hoặc bổ sung adapter tại ranh giới. Mục tiêu là giữ cho mỗi tầng phụ thuộc vào những hợp đồng cần thiết để thực hiện trách nhiệm của mình, đồng thời duy trì đồ thị dễ hiểu và có thể kiểm chứng.
