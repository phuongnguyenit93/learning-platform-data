# Phân biệt lỗi nghiệp vụ với lỗi thành phần cộng tác

Một test đơn vị thường kiểm tra một đối tượng hoặc một nhóm logic nhỏ trong điều kiện các dependency được kiểm soát. Khi test thất bại, câu hỏi quan trọng là: logic của đối tượng đang kiểm tra có quyết định sai, hay một thành phần mà nó cộng tác đang cung cấp kết quả sai, được gọi sai hoặc không hoạt động như mong đợi?

Hai loại lỗi này có thể tạo ra cùng một biểu hiện bên ngoài. Ví dụ, một đơn hàng bị từ chối có thể do quy tắc nghiệp vụ không cho phép đặt số lượng đó, do kho báo hết hàng, do adapter truy vấn tồn kho sai, hoặc do test đã cấu hình mock không đúng. Muốn tìm đúng nguyên nhân, cần xác định ranh giới của unit test, kiểm soát kết quả từ collaborator và kiểm tra từng thành phần ở phạm vi phù hợp.

## Hai nhóm lỗi khác nhau ở đâu?

**Lỗi nghiệp vụ** xảy ra khi quy tắc hoặc quyết định mà ứng dụng phải thực hiện không đúng. Ví dụ: tính tổng tiền sai, áp dụng giảm giá sai điều kiện, cho phép số lượng không hợp lệ, chuyển trạng thái đơn hàng sai hoặc trả về kết quả không phù hợp với chính sách nghiệp vụ.

**Lỗi thành phần cộng tác** xảy ra khi một dependency không thực hiện đúng trách nhiệm của nó hoặc khi đối tượng đang kiểm tra phối hợp với dependency sai cách. Ví dụ: repository truy vấn nhầm bản ghi, adapter chuyển đổi dữ liệu sai, cổng tồn kho gửi sai mã sản phẩm, client HTTP ánh xạ response sai, bean không được cấu hình hoặc inject như dự kiến.

Cần phân biệt hai khái niệm:

- *Collaborator* là một đối tượng hoặc dịch vụ mà unit đang kiểm tra gọi đến để hoàn thành công việc.
- *Component* là một phần triển khai có ranh giới và trách nhiệm riêng, có thể là repository, adapter, client, service hoặc một bean Spring.

Một collaborator có thể được thay bằng mock trong unit test. Khi đó test đang kiểm tra cách unit sử dụng collaborator theo hợp đồng đã khai báo, chứ chưa kiểm tra triển khai thật của collaborator.

| Dấu hiệu quan sát | Khả năng cần điều tra |
|---|---|
| Collaborator trả về đúng dữ liệu đã được test quy định, nhưng kết quả nghiệp vụ sai | Quy tắc hoặc phép tính trong unit đang kiểm tra |
| Unit truyền sai tham số, gọi thiếu hoặc gọi collaborator sai thời điểm | Logic phối hợp của unit |
| Collaborator thật trả về dữ liệu sai ngay cả khi được gọi độc lập với đầu vào hợp lệ | Lỗi triển khai của collaborator |
| Unit test chạy tốt với mock nhưng test tích hợp thất bại | Hợp đồng, cấu hình, wiring hoặc tương tác giữa các thành phần thật |
| Test thất bại vì mock không được stub đúng hoặc fixture mâu thuẫn | Lỗi thiết lập test; chưa đủ căn cứ kết luận code sản phẩm sai |

Không nên chỉ nhìn tên exception hoặc dòng assertion đầu tiên rồi kết luận nguyên nhân. Cần xem đầu vào, kết quả mà collaborator cung cấp, các lời gọi thực tế và phạm vi mà test đang bao phủ.

## Xác định ranh giới unit đang kiểm tra

Giả sử ứng dụng có luồng đặt hàng:

1. Nhận mã sản phẩm và số lượng.
2. Đọc thông tin sản phẩm từ catalog.
3. Tính tổng tiền.
4. Yêu cầu hệ thống kho giữ hàng.
5. Lưu đơn hàng.

Trong luồng này, `OrderService` có thể là unit đang được kiểm tra. Catalog, inventory và repository là các collaborator của nó.

~~~mermaid
flowchart TD
    A["OrderService"] --> B["ProductCatalog"]
    A --> C["Inventory"]
    A --> D["OrderRepository"]
    A --> E["Quy tắc đặt hàng và tính tổng"]
~~~

Nếu mục tiêu là kiểm tra quy tắc của `OrderService`, test có thể thay catalog, inventory và repository bằng test double. Nhờ vậy, test kiểm soát được sản phẩm nào được tìm thấy, kho có chấp nhận giữ hàng hay không và repository trả về gì.

Nếu mục tiêu là kiểm tra `ProductCatalog` truy vấn database đúng, cần một test riêng cho triển khai catalog thật với database test phù hợp. Mock catalog trong `OrderServiceTest` không thể chứng minh câu SQL, mapping hoặc transaction của catalog thật là đúng.

Ranh giới test cần được viết rõ trong tên và cấu trúc test. Một test mang tên `calculatesTotalForAvailableProduct` nên tập trung vào quyết định tính tiền. Một test mang tên `jdbcProductCatalogFindsProductBySku` nên kiểm tra adapter truy vấn dữ liệu. Khi một test cố kiểm tra mọi thứ cùng lúc, việc phân loại nguyên nhân thất bại sẽ khó hơn.

## Kiểm tra logic nghiệp vụ khi collaborator được kiểm soát

Ví dụ dưới đây minh họa một service có quy tắc kiểm tra số lượng, tìm sản phẩm, tính tổng tiền và yêu cầu kho giữ hàng:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

record Product(String sku, BigDecimal unitPrice) {}

record OrderCommand(String sku, int quantity) {}

record Order(
    String sku,
    int quantity,
    BigDecimal total
) {}

interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}

interface Inventory {
    boolean reserve(String sku, int quantity);
}

interface OrderRepository {
    Order save(Order order);
}

class OrderService {
    private final ProductCatalog catalog;
    private final Inventory inventory;
    private final OrderRepository repository;

    OrderService(
        ProductCatalog catalog,
        Inventory inventory,
        OrderRepository repository
    ) {
        this.catalog = catalog;
        this.inventory = inventory;
        this.repository = repository;
    }

    Order place(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        Product product = catalog.findBySku(command.sku())
            .orElseThrow(() -> new ProductNotFoundException(command.sku()));

        BigDecimal total = product.unitPrice()
            .multiply(BigDecimal.valueOf(command.quantity()));

        if (!inventory.reserve(command.sku(), command.quantity())) {
            throw new OutOfStockException(command.sku());
        }

        return repository.save(
            new Order(command.sku(), command.quantity(), total)
        );
    }
}
~~~

Các exception `ProductNotFoundException` và `OutOfStockException` là exception nghiệp vụ giả định của ví dụ. Điều cần chú ý là trách nhiệm được phân chia: service kiểm tra số lượng và điều phối luồng; catalog tìm sản phẩm; inventory giữ hàng; repository lưu đơn.

Trong unit test, có thể dùng Mockito để quy định kết quả của các collaborator:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    ProductCatalog catalog;

    @Mock
    Inventory inventory;

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @Test
    void calculatesTotalAndSavesOrder() {
        when(catalog.findBySku("SKU-1"))
            .thenReturn(Optional.of(
                new Product("SKU-1", new BigDecimal("12.50"))
            ));
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Order result = service.place(new OrderCommand("SKU-1", 2));

        assertThat(result.total())
            .isEqualByComparingTo("25.00");
        assertThat(result.quantity()).isEqualTo(2);

        verify(inventory).reserve("SKU-1", 2);
        verify(repository).save(any(Order.class));
    }
}
~~~

Ở đây test chủ động đặt kết quả của catalog và inventory. Nếu service trả về tổng tiền `24.00` thay vì `25.00`, nguyên nhân nằm trong logic tính tiền của unit đang kiểm tra, với điều kiện fixture và kỳ vọng trong test là chính xác. Collaborator không tự truy vấn database hoặc gọi dịch vụ kho thật nên không thể quy lỗi cho các triển khai đó.

Các test khác có thể kiểm tra các nhánh nghiệp vụ:

~~~java
@Test
void rejectsZeroQuantity() {
    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 0))
    ).isInstanceOf(IllegalArgumentException.class);
}

@Test
void rejectsOrderWhenInventoryCannotReserve() {
    when(catalog.findBySku("SKU-1"))
        .thenReturn(Optional.of(
            new Product("SKU-1", new BigDecimal("12.50"))
        ));
    when(inventory.reserve("SKU-1", 2)).thenReturn(false);

    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 2))
    ).isInstanceOf(OutOfStockException.class);

    verify(repository, never()).save(any(Order.class));
}
~~~

Đoạn test thứ hai xác nhận quyết định của service khi collaborator báo không giữ được hàng: service phát sinh kết quả nghiệp vụ hết hàng và không lưu đơn. Nó không chứng minh thuật toán kiểm tra tồn kho trong hệ thống kho thật hoạt động đúng; test đang kiểm tra cách service phản ứng với hợp đồng `Inventory.reserve()`.

Các import và class exception cần được khai báo tương ứng trong một project thực tế; đoạn code tập trung minh họa cách đặt ranh giới test và kiểm soát collaborator.

## Khi nào một lỗi thuộc về collaborator?

Mock giúp kiểm soát đầu vào của unit, nhưng nếu mock trả về kết quả sai do test stub sai thì test có thể thất bại dù code sản phẩm đúng. Vì vậy, cần phân biệt ba tình huống:

**Collaborator được stub đúng, unit dùng sai.** Ví dụ, test quy định `reserve("SKU-1", 2)` trả về `true`, nhưng service lại gọi `reserve("SKU-1", 1)`. Đây là lỗi phối hợp trong unit đang kiểm tra, bởi đối số truyền đi không khớp yêu cầu.

**Collaborator được gọi đúng, nhưng triển khai thật trả về sai.** Ví dụ, service truyền đúng mã SKU, nhưng `JdbcProductCatalog` truy vấn nhầm cột hoặc ánh xạ sai giá. Đây là lỗi cần điều tra trong catalog adapter và kiểm chứng bằng test của chính adapter.

**Mock hoặc fixture được cấu hình sai.** Ví dụ, service tìm `SKU-1`, nhưng test lại stub `findBySku("SKU-01")`. Mock có thể trả về giá trị mặc định, làm test đi vào nhánh không mong muốn. Đây là lỗi thiết lập test, không phải bằng chứng rằng service sai.

Có thể dùng `ArgumentCaptor` để xem object mà unit thực sự gửi cho collaborator:

~~~java
ArgumentCaptor<Order> captor = ArgumentCaptor.forClass(Order.class);

verify(repository).save(captor.capture());

Order saved = captor.getValue();

assertThat(saved.sku()).isEqualTo("SKU-1");
assertThat(saved.quantity()).isEqualTo(2);
assertThat(saved.total()).isEqualByComparingTo("25.00");
~~~

Captor hữu ích khi nội dung được truyền đi là một phần hợp đồng cộng tác. Tuy nhiên, không nên kiểm tra mọi lời gọi nội bộ. Test quá phụ thuộc vào chi tiết tương tác sẽ dễ vỡ khi refactor mà hành vi nghiệp vụ bên ngoài vẫn đúng.

## Test collaborator thật ở phạm vi phù hợp

Nếu nghi ngờ lỗi nằm trong một thành phần cộng tác, hãy kiểm tra thành phần đó với dependency thật hoặc test double phù hợp với ranh giới của nó.

Ví dụ, `JdbcProductCatalog` cần được kiểm tra với database test để xác nhận:

- SQL lọc đúng SKU.
- Mapping các cột thành `Product` đúng.
- Không tìm thấy bản ghi thì trả về `Optional.empty()`.
- Kiểu dữ liệu và giá trị tiền tệ được đọc chính xác.
- Transaction và xử lý lỗi database phù hợp với hợp đồng của adapter.

Một unit test cho service với mock catalog không bao phủ các điểm này.

Có thể dùng Spring Test để nạp cấu hình persistence cần thiết, tạo database test và inject catalog thật vào test:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class JdbcProductCatalogTest {

    @Autowired
    ProductCatalog catalog;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void findsProductAndMapsItsPrice() {
        jdbcTemplate.update(
            "insert into product(sku, unit_price) values (?, ?)",
            "SKU-1",
            new BigDecimal("12.50")
        );

        var result = catalog.findBySku("SKU-1");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().unitPrice())
            .isEqualByComparingTo("12.50");
    }
}
~~~

Ví dụ giả định `PersistenceTestConfig` cấu hình datasource, schema, transaction manager và bean `JdbcProductCatalog`; cấu trúc bảng tương ứng có hai cột `sku` và `unit_price`. Transaction test-managed giúp hoàn tác dữ liệu test sau khi method kết thúc.

Nếu test catalog thật thất bại do mapping giá sai, có bằng chứng cụ thể để điều tra adapter. Nếu test catalog thành công nhưng `OrderServiceTest` thất bại khi các kết quả collaborator đã được stub đúng, hãy tập trung vào logic hoặc cách điều phối của service.

Với adapter HTTP, có thể dùng mock web server hoặc HTTP stub để kiểm tra request, response và mapping. Với message publisher, có thể kiểm tra message được tạo đúng và dùng integration test để xác nhận broker nhận được message. Chọn công cụ theo trách nhiệm của component.

## Phân biệt lỗi nghiệp vụ với lỗi kỹ thuật từ collaborator

Không phải mọi lỗi collaborator đều là lỗi nghiệp vụ. Cần phân biệt kết quả nghiệp vụ hợp lệ với lỗi kỹ thuật khiến collaborator không thể thực hiện trách nhiệm:

| Tình huống | Phân loại kết quả |
|---|---|
| Kho xác nhận không đủ hàng | Kết quả nghiệp vụ: không thể đặt hàng |
| Catalog không tìm thấy sản phẩm | Kết quả nghiệp vụ hoặc dữ liệu đầu vào không hợp lệ, tùy hợp đồng |
| Database mất kết nối khi lưu đơn | Lỗi kỹ thuật của hạ tầng hoặc repository |
| HTTP client nhận response sai định dạng | Lỗi giao tiếp hoặc mapping của adapter |
| Service tính tổng tiền sai khi catalog trả đúng đơn giá | Lỗi logic nghiệp vụ của service |
| Service truyền sai mã sản phẩm sang inventory | Lỗi phối hợp giữa service và collaborator |

Một lỗi kỹ thuật có thể được chuyển thành exception hoặc kết quả ở tầng trên theo chính sách của ứng dụng. Nhưng việc chuyển đổi phải giữ được ý nghĩa. Không nên bắt mọi exception rồi trả về `OutOfStockException`, vì khi đó mất khả năng phân biệt kho thật sự hết hàng với việc hệ thống kho không truy cập được.

Test nên kiểm tra cả cách xử lý lỗi kỹ thuật nếu đó là trách nhiệm của unit:

~~~java
@Test
void propagatesInventoryInfrastructureFailure() {
    when(catalog.findBySku("SKU-1"))
        .thenReturn(Optional.of(
            new Product("SKU-1", new BigDecimal("12.50"))
        ));
    when(inventory.reserve("SKU-1", 2))
        .thenThrow(new InventoryUnavailableException());

    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 2))
    ).isInstanceOf(InventoryUnavailableException.class);

    verify(repository, never()).save(any(Order.class));
}
~~~

Test này xác nhận service không lưu đơn khi hệ thống kho không thể trả lời. Nó giúp ngăn code biến lỗi hạ tầng thành một quyết định nghiệp vụ sai.

## Cách đọc kết quả test để khoanh vùng nguyên nhân

Khi một test thất bại, hãy lần theo luồng dữ liệu và xác định giá trị đầu tiên khác với hợp đồng mong đợi.

1. **Xác nhận test đang kiểm tra unit nào.** Xác định method, đầu vào, kết quả mong đợi và collaborator nào được thay bằng mock hoặc fake.
2. **Kiểm tra fixture và stub.** Đảm bảo mock được cấu hình đúng đối số, đúng giá trị trả về và đúng exception.
3. **Kiểm tra kết quả của collaborator.** Nếu dùng mock, giá trị do test quy định là gì? Nếu dùng component thật, component nhận đầu vào gì và trả về gì?
4. **Kiểm tra lời gọi cộng tác.** Unit có truyền đúng dữ liệu, gọi đủ collaborator và tuân thủ thứ tự mà hợp đồng yêu cầu không?
5. **Chạy test riêng cho component nghi ngờ.** Dùng database, HTTP stub, broker hoặc context phù hợp để xác minh triển khai thật.
6. **Kiểm tra wiring và cấu hình nếu lỗi chỉ xuất hiện khi tích hợp.** Xem bean nào được inject, profile/property nào đang có hiệu lực và adapter nào thực sự được dùng.

Bảng dưới đây gợi ý phạm vi tiếp theo:

| Nơi phát hiện lỗi | Phạm vi nên kiểm tra tiếp |
|---|---|
| Unit test với collaborator đã stub | Logic unit, fixture, đối số và quy tắc phối hợp |
| Test adapter với dependency thật | SQL, mapping, giao thức, cấu hình và xử lý lỗi của adapter |
| Spring context hoặc slice test | Bean registration, dependency injection, profile, property và auto-configuration |
| Integration test giữa nhiều thành phần | Hợp đồng và dữ liệu đi qua ranh giới giữa các component |
| Chỉ lỗi ở môi trường triển khai | Cấu hình môi trường, credential, endpoint, network và dịch vụ phụ thuộc |

Không cần chạy toàn bộ hệ thống ngay khi một unit test thất bại. Bắt đầu từ test có phạm vi hẹp nhất có thể tái hiện sai lệch, rồi mở rộng khi bằng chứng cho thấy lỗi nằm ở ranh giới cộng tác.

## Tránh hai cực đoan khi dùng mock

**Mock mọi collaborator** khiến test chạy nhanh và cô lập, nhưng có thể tạo ra một thế giới giả định: mọi dependency đều trả về đúng điều test muốn. Một service có thể vượt qua toàn bộ unit test trong khi SQL sai, bean không được đăng ký hoặc HTTP adapter không đọc được response thật.

**Không mock collaborator nào** có thể khiến một test được gọi là unit test nhưng thực chất khởi động database, web server và nhiều dịch vụ. Khi thất bại, khó biết lỗi thuộc logic đang kiểm tra hay một dependency bên ngoài.

Một cách cân bằng:

- Giữ các object domain và logic thuần Java thật khi chúng là một phần của quy tắc đang kiểm tra.
- Thay các ranh giới I/O hoặc dịch vụ bên ngoài bằng mock, stub hoặc fake trong unit test.
- Viết test riêng cho adapter và component có triển khai kỹ thuật quan trọng.
- Dùng Spring Test hoặc Spring Boot Test khi cần kiểm chứng wiring, cấu hình và tương tác thật giữa bean.
- Bổ sung integration test cho những hợp đồng quan trọng giữa các thành phần.

Không phải collaborator nào cũng cần mock. Nếu một collaborator nhỏ, thuần Java và ổn định, dùng triển khai thật có thể giúp test thể hiện quy tắc gần với hành vi thực tế hơn. Điều quan trọng là biết test đang bao phủ phần nào và phần nào vẫn cần test riêng.

## Lỗi trong test không đồng nghĩa lỗi trong sản phẩm

Bản thân test cũng có thể sai: expected value tính nhầm, fixture không hợp lệ, mock stub sai, test dùng chung state hoặc assertion kiểm tra một chi tiết triển khai không thuộc hợp đồng.

Khi test thất bại, không nên sửa code sản phẩm chỉ để làm test xanh trước khi xác nhận test mô tả đúng yêu cầu. Ngược lại, cũng không nên sửa expected value để chấp nhận hành vi sai. Hãy đối chiếu với quy tắc nghiệp vụ và hợp đồng collaborator, rồi xác định đâu là nguồn dữ liệu đáng tin cậy.

Tên test nên diễn đạt hành vi và điều kiện cụ thể, ví dụ:

- `rejectsOrderWhenQuantityIsNotPositive`
- `doesNotSaveOrderWhenInventoryCannotReserve`
- `passesRequestedQuantityToInventory`
- `mapsDatabasePriceToProductUnitPrice`
- `propagatesInventoryUnavailableFailure`

Tên rõ ràng giúp người đọc hiểu test đang chứng minh quy tắc nghiệp vụ, hợp đồng phối hợp hay triển khai của một component.

## Nguyên tắc áp dụng khi thiết kế unit test

Trước khi kết luận một test thất bại do nghiệp vụ hay collaborator, hãy xác định:

- Unit đang kiểm tra và trách nhiệm của nó là gì?
- Collaborator nào được dùng thật, collaborator nào được thay bằng test double?
- Đầu vào và kết quả của từng collaborator có đúng với hợp đồng không?
- Unit có đưa ra quyết định nghiệp vụ đúng trên những kết quả đó không?
- Nếu dùng component thật, test có cô lập và kiểm soát được database, network hoặc tài nguyên liên quan không?
- Test nào chứng minh triển khai của collaborator hoạt động đúng?
- Nếu cần Spring, test đã nạp đúng context, bean, profile và property chưa?

Lỗi nghiệp vụ được xác định bằng cách kiểm tra quyết định của ứng dụng trên đầu vào và kết quả collaborator đã biết. Lỗi thành phần cộng tác được xác định bằng cách kiểm tra hợp đồng, lời gọi và triển khai của dependency ở ranh giới riêng. Kết hợp unit test cô lập với test component và integration test có phạm vi rõ ràng giúp tìm đúng nơi gây lỗi, đồng thời tránh để mock tạo ra cảm giác an toàn giả.
