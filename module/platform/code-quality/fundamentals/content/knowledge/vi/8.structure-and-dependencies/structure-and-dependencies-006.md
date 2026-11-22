# Chu kỳ phụ thuộc và ảnh hưởng đến kiểm thử, thay đổi

Một lớp Java gọi lớp khác là điều bình thường. Vấn đề xuất hiện khi các thành phần **phụ thuộc vòng quanh nhau**: A cần B, B cần C, rồi C lại cần A. Khi đó, một thay đổi tưởng như cục bộ có thể buộc nhiều phần cùng được hiểu, kiểm thử hoặc triển khai; việc tạo đối tượng, tách mô-đun và xử lý lỗi cũng có thể trở nên khó khăn.

Bài học thuộc chương **Cấu trúc và phụ thuộc** của **CODE_QUALITY_FUNDAMENTALS**, hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Chúng ta sẽ học cách nhận diện chu kỳ phụ thuộc, đánh giá tác động thực tế và lựa chọn cách tháo gỡ có kiểm chứng.

## 1. Phụ thuộc là gì?

**Phụ thuộc (dependency)** là quan hệ trong đó một thành phần cần đến một thành phần khác để biên dịch, thực thi hoặc hoàn thành một trách nhiệm. Trong mã Java, phụ thuộc có thể xuất hiện qua việc dùng kiểu dữ liệu, gọi phương thức, kế thừa, tạo đối tượng, khai báo tham số hoặc cấu hình liên kết thành phần.

Ví dụ:

~~~java
interface ProductRepository {
    Product findBySku(String sku);
}

final class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    Product load(String sku) {
        return repository.findBySku(sku);
    }
}
~~~

Ở đây, `ProductService` phụ thuộc vào **hợp đồng** `ProductRepository`. Quan hệ đó tự thân không xấu: dịch vụ cần một nguồn dữ liệu để hoàn thành công việc. Điều cần quan sát là **phụ thuộc đi theo hướng nào**, **hợp đồng có ổn định không** và **khi thay đổi một phần, bao nhiêu phần bị ảnh hưởng**.

Để biểu diễn, quy ước mũi tên **A → B** nghĩa là “A phụ thuộc vào B”. Khi vẽ sơ đồ, phải nói rõ đang xét phụ thuộc mã nguồn, phụ thuộc lúc dựng đối tượng, tham chiếu giữa module hay lời gọi lúc chạy. Những loại đồ thị này có thể khác nhau.

## 2. Chu kỳ phụ thuộc là gì?

**Chu kỳ phụ thuộc (dependency cycle)** tồn tại khi có đường đi theo hướng mũi tên xuất phát từ một thành phần rồi quay về chính thành phần đó qua một hoặc nhiều quan hệ phụ thuộc.

Ví dụ:

~~~mermaid
flowchart LR
    A[OrderService] --> B[PaymentService]
    B --> C[CustomerService]
    C --> A
~~~

Trong đồ thị này:

- `OrderService` cần `PaymentService`.
- `PaymentService` cần `CustomerService`.
- `CustomerService` lại cần `OrderService`.

Ba thành phần không thể được hiểu hoàn toàn độc lập theo các quan hệ đang xét. Một thay đổi ở hợp đồng của `OrderService` có thể ảnh hưởng `CustomerService`; từ đó chuỗi tác động có thể quay về chính `OrderService`.

Cần phân biệt:

| Tình huống | Có phải chu kỳ phụ thuộc? | Ghi chú |
| --- | --- | --- |
| A → B → C | Không | Đồ thị có hướng không có đường quay về A |
| A → B → A | Có | Chu kỳ trực tiếp giữa hai thành phần |
| A → B → C → A | Có | Chu kỳ gián tiếp |
| A → B, C → B | Không | Nhiều nơi cùng dùng B không tạo chu kỳ |
| Một phương thức tự gọi đệ quy | Chưa đủ kết luận | Đệ quy của luồng gọi không đồng nghĩa chu kỳ phụ thuộc giữa các thành phần |
| Hai dịch vụ gọi HTTP qua lại | Có thể là chu kỳ lúc chạy | Chưa chắc tạo chu kỳ phụ thuộc biên dịch nếu chỉ dùng hợp đồng bên ngoài |

Đối với đồ thị có hướng, một **thành phần liên thông mạnh (strongly connected component, SCC)** gồm các nút có thể đi đến nhau theo đường có hướng. SCC chứa từ hai nút trở lên chắc chắn có chu kỳ; một SCC chỉ có một nút chỉ là chu kỳ nếu có cạnh tự trỏ. Đây là nền tảng của nhiều công cụ phát hiện vòng phụ thuộc.

## 3. Chu kỳ xuất hiện ở những cấp độ nào?

### 3.1. Cấp lớp

Hai lớp trực tiếp giữ tham chiếu đến nhau hoặc gọi phương thức của nhau:

~~~java
final class OrderService {
    private final PaymentService paymentService;

    OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    // ...
}

final class PaymentService {
    private final OrderService orderService;

    PaymentService(OrderService orderService) {
        this.orderService = orderService;
    }

    // ...
}
~~~

Quan hệ là `OrderService → PaymentService → OrderService`. Nếu cả hai bắt buộc nhận nhau qua constructor, việc tạo trực tiếp hai đối tượng sẽ bị kẹt về thứ tự khởi tạo. Một số container dependency injection cũng từ chối chu kỳ constructor; các cách dùng tham chiếu trễ hoặc setter có thể né lỗi khởi tạo nhưng **không tự giải quyết ràng buộc thiết kế**.

Tuy nhiên, chỉ nhìn thấy hai lớp có tham chiếu qua lại chưa đủ kết luận xảy ra vòng gọi vô hạn. **Chu kỳ phụ thuộc** và **đệ quy vô hạn lúc chạy** là hai vấn đề khác nhau.

### 3.2. Cấp package

Ví dụ:

~~~text
com.example.order      → com.example.payment
com.example.payment    → com.example.customer
com.example.customer   → com.example.order
~~~

Trong Java, việc một vài lớp trong các package này import kiểu của nhau có thể tạo chu kỳ package mà trình biên dịch vẫn xử lý được, tùy cách tổ chức nguồn và build. Chu kỳ package có thể làm ranh giới trách nhiệm thiếu rõ: đâu là lớp nghiệp vụ cốt lõi, đâu là thành phần điều phối, đâu là hợp đồng?

Một lần refactor phá chu kỳ giữa **lớp** chưa chắc đã phá chu kỳ giữa **package** nếu các lớp khác vẫn còn nhập chéo.

### 3.3. Cấp module và build

Với các module hoặc tiểu dự án có quan hệ build, một chu kỳ như `module-a → module-b → module-a` có thể khiến việc xác định thứ tự biên dịch, đóng gói hoặc phát hành không khả thi. Công cụ build hoặc hệ thống mô-đun Java có những quy tắc ngăn dạng phụ thuộc vòng ở ranh giới module.

Do đó cần kiểm tra **đồ thị module thực tế**. Việc các package trong cùng một module phụ thuộc vòng có thể không gây lỗi build ngay, nhưng vẫn tác động tới kiến trúc và kiểm thử. Ngược lại, không có chu kỳ build cũng **không chứng minh** không có chu kỳ tương tác ở runtime.

### 3.4. Cấp dịch vụ và workflow

Dịch vụ A có thể gửi yêu cầu cho B, B gửi tiếp cho C, C lại gọi A để hoàn thành cùng một giao dịch. Đây là vòng trong **đồ thị tương tác**. Nó có thể làm tăng độ trễ, tạo lỗi lan truyền, khó xác định deadline hoặc gây vòng gọi lặp trong một số điều kiện.

Không nên trộn biểu đồ runtime này với chu kỳ import Java: một hệ thống không có import vòng vẫn có thể tạo vòng HTTP hoặc sự kiện. Cách xử lý thường liên quan đến thiết kế workflow, trách nhiệm nghiệp vụ, idempotency và quản lý trạng thái, bên cạnh cấu trúc mã.

## 4. Vì sao chu kỳ khiến mã khó hiểu?

Hãy xem đồ thị phụ thuộc không vòng:

~~~mermaid
flowchart LR
    A[PriceQuoteService] --> B[CatalogReader]
    A --> C[DiscountPolicy]
    B --> D[Product]
    C --> D
~~~

Người đọc có thể bắt đầu ở `PriceQuoteService`, hiểu vai trò `CatalogReader` và `DiscountPolicy`, rồi lần theo `Product`. Các thành phần phía dưới không cần biết dịch vụ điều phối ở phía trên tồn tại.

Khi phụ thuộc có vòng, việc hiểu A buộc phải xem B, rồi C, rồi quay lại A. Ranh giới khái niệm bị mờ vì mỗi thành phần vừa dùng vừa bị dùng trong cùng một nhóm:

- **Ngữ cảnh cần giữ trong đầu tăng:** hiểu hành vi A có thể phải hiểu một phần trạng thái và quyết định của B.
- **Lý do thay đổi không rõ:** một quy tắc của A có thể được triển khai một phần ở B.
- **Tác dụng phụ khó thấy:** B có thể gọi lại A, làm thay đổi trạng thái trong lúc A vẫn đang xử lý.
- **Hợp đồng khó ổn định:** thay đổi một giao diện tác động ngay tới thành phần lẽ ra ở phía khác của ranh giới.

Chu kỳ là **tín hiệu cần điều tra**, không phải bằng chứng mọi mã trong chu kỳ đều sai. Hai đối tượng trong một cấu trúc dữ liệu hai chiều có thể tham chiếu nhau một cách hợp lý. Điều cần đánh giá là liệu ranh giới đó có làm người bảo trì phải hiểu và thay đổi quá nhiều trách nhiệm cùng lúc hay không.

## 5. Tác động tới kiểm thử

### 5.1. Khó khởi tạo đối tượng trong unit test

Với `OrderService(PaymentService)` và `PaymentService(OrderService)`, test không thể tạo đầy đủ cả hai chỉ bằng cách lần lượt gọi constructor mà không có một cách phá vòng hoặc trì hoãn liên kết.

Người viết test dễ phải dùng container DI, factory phức tạp, mock nhiều tầng hoặc setter để dựng một đối tượng chỉ nhằm kiểm tra một quy tắc đơn giản. **Chi phí setup test tăng** là tín hiệu ranh giới trách nhiệm có thể chưa tốt.

### 5.2. Mock có thể che giấu phụ thuộc thật

Mock một thành phần trong vòng giúp test chạy, nhưng không đảm bảo các tương tác hai chiều ngoài đời vẫn đúng. Ví dụ, test chỉ xác nhận `PaymentService` gọi `OrderService.markPaid()`, trong khi luồng thật còn phụ thuộc transaction, retry và lỗi mạng.

Mock phù hợp để cô lập trách nhiệm, nhưng nếu muốn xác minh một **workflow vượt nhiều thành phần**, vẫn cần test tích hợp hoặc test hợp đồng phù hợp. Đừng dùng số lượng mock lớn như bằng chứng tự thân rằng thiết kế tốt hay xấu; hãy xem **điều gì buộc test phải biết**.

### 5.3. Khó xác định phạm vi hồi quy

Khi A, B, C cùng nằm trong SCC, sửa A có thể cần xem tác động ngược từ C và B. Bộ kiểm thử có xu hướng phải chạy rộng hơn để tin rằng thay đổi không phá luồng khác.

Rủi ro càng cao khi các thành phần cùng giữ trạng thái chia sẻ hoặc gọi lại lẫn nhau. Một test riêng A có thể qua, nhưng chuỗi tương tác A → B → C → A vẫn thất bại khi tích hợp.

### 5.4. Những biểu hiện thường thấy

| Triệu chứng trong test | Vấn đề có thể nằm sau | Câu hỏi nên hỏi |
| --- | --- | --- |
| Cần dựng nhiều service không liên quan cho một phép tính thuần | Trách nhiệm bị trộn vào orchestration hoặc phụ thuộc vòng | Quy tắc có thể tách khỏi I/O và điều phối không? |
| Test khởi tạo bean/container báo vòng tham chiếu | Chu kỳ ở đồ thị đối tượng | Constructor và hợp đồng nên hướng theo chiều nào? |
| Mock xong A nhưng test B vẫn phải cấu hình A | B đang biết quá nhiều về phần cần cô lập | Có thể truyền dữ liệu hoặc một hợp đồng hẹp không? |
| Chỉ chạy unit test thì ổn, test tích hợp thất bại | Tương tác ngoài ranh giới chưa được bảo vệ | Cần contract/integration test cho luồng nào? |
| Thay một lớp khiến test nhiều package cùng lỗi | Phụ thuộc lan rộng | Hợp đồng chung có đang thay đổi thường xuyên không? |

**Không phải mọi test khó là do chu kỳ.** Tài nguyên ngoài, trạng thái tĩnh, thời gian, concurrency và giao diện quá lớn cũng có thể gây khó kiểm thử. Cần xác định đường phụ thuộc thực trước khi chọn refactor.

## 6. Tác động tới thay đổi và phát hành

### 6.1. Mức lan truyền khi sửa hợp đồng tăng

Nếu A, B và C cùng trong một nhóm phụ thuộc vòng, thay đổi kiểu dữ liệu hoặc chữ ký phương thức ở A có thể buộc sửa B; việc sửa B lại buộc sửa C và ảnh hưởng trở lại A. Vì vậy, dù yêu cầu mới chỉ nằm ở một chức năng, phạm vi kiểm thử và review có thể mở rộng.

Điều này làm giảm **khả năng thay đổi cục bộ**, một thành phần quan trọng của chất lượng mã dài hạn.

### 6.2. Tính độc lập của module bị giảm

Khi package hoặc module liên tục import chéo, rất khó tách một phần làm thư viện dùng chung, chuyển sang module riêng hoặc giao cho nhóm khác bảo trì độc lập. Ranh giới sở hữu không trùng với ranh giới phụ thuộc.

Ở runtime, vòng gọi giữa các dịch vụ cũng có thể làm việc triển khai độc lập khó hơn: thay đổi contract ở A và B phải phối hợp phiên bản hoặc cơ chế tương thích.

### 6.3. Nguy cơ khi khởi tạo và vận hành

Chu kỳ constructor có thể gây lỗi tạo bean. Chu kỳ trong static initialization hoặc callback có thể tạo hành vi khó dự đoán nếu các đối tượng được dùng trước khi hoàn tất khởi tạo. Trong hệ phân tán, các vòng đồng bộ có thể khiến timeout và lỗi lan truyền theo dây chuyền.

Các nguy cơ này **không tự động xảy ra ở mọi chu kỳ**. Cần kiểm tra loại phụ thuộc cụ thể: import kiểu đơn thuần có tính chất khác với lời gọi đồng bộ, chia sẻ trạng thái hoặc gọi callback.

## 7. Ví dụ xuyên suốt bằng Java: giá sản phẩm và chính sách giảm giá

Giả sử ứng dụng cần trả **giá hiển thị** của sản phẩm. Khi khách VIP và sản phẩm đủ điều kiện, chính sách giảm **10%**, làm tròn xuống số VND nguyên. Ta chỉ xem phần đọc dữ liệu và tính giá; đặt hàng hay trừ tiền là luồng khác.

### 7.1. Thiết kế có vòng phụ thuộc

Một thiết kế ban đầu có thể như sau (mã rút gọn minh họa quan hệ; phần truy cập kho dữ liệu chưa được triển khai):

~~~java
final class CatalogService {
    private final DiscountService discounts;

    CatalogService(DiscountService discounts) {
        this.discounts = discounts;
    }

    long displayPriceVnd(String sku, boolean vip) {
        return discounts.priceFor(sku, vip);
    }

    Product findBySku(String sku) {
        // Đọc dữ liệu sản phẩm từ nguồn lưu trữ.
        throw new UnsupportedOperationException("Illustration only");
    }
}

final class DiscountService {
    private final CatalogService catalog;

    DiscountService(CatalogService catalog) {
        this.catalog = catalog;
    }

    long priceFor(String sku, boolean vip) {
        Product product = catalog.findBySku(sku);
        long price = product.priceVnd();
        return vip && product.eligibleForVipDiscount()
                ? price - price / 10
                : price;
    }
}
~~~

Đồ thị là:

~~~mermaid
flowchart LR
    A[CatalogService] --> B[DiscountService]
    B --> A
~~~

Vấn đề nằm ở **hướng trách nhiệm**:

- `CatalogService` cần `DiscountService` để hiển thị giá.
- `DiscountService` lại biết toàn bộ `CatalogService` chỉ để đọc thông tin sản phẩm.
- Hai constructor đòi đối tượng của nhau, khiến việc dựng trực tiếp bằng constructor không thể hoàn tất bằng một chuỗi tạo đối tượng thông thường.
- Unit test chính sách giảm giá bị phụ thuộc vào cách khởi tạo `CatalogService`.

Đoạn mã không nhất thiết dẫn đến đệ quy vô hạn: `displayPriceVnd` gọi `priceFor`, rồi `priceFor` gọi `findBySku` và có thể kết thúc. **Vòng tham chiếu thiết kế** tồn tại ngay cả khi luồng gọi này hữu hạn.

### 7.2. Làm rõ hướng phụ thuộc

Ta tách ba trách nhiệm:

1. **Đọc sản phẩm:** hợp đồng `ProductReader`, không cần biết chính sách giảm giá.
2. **Tính giá:** `DiscountPolicy`, một hàm tính toán dùng dữ liệu `Product`.
3. **Điều phối:** `PriceQuoteService` lấy sản phẩm rồi gọi chính sách.

Đồ thị mới:

~~~mermaid
flowchart LR
    Q[PriceQuoteService] --> R[ProductReader]
    Q --> D[DiscountPolicy]
    R --> P[Product]
    D --> P
~~~

Không còn đường phụ thuộc quay về `PriceQuoteService`. Mỗi phần có mục đích rõ và có thể được kiểm thử theo trách nhiệm.

### 7.3. Phiên bản Java sau khi tách

Ví dụ sử dụng Java 17+ để khai báo `record`:

~~~java
import java.util.Objects;

record Product(String sku, long priceVnd,
               boolean eligibleForVipDiscount) {}

interface ProductReader {
    Product findBySku(String sku);
}

final class DiscountPolicy {
    long finalPriceVnd(Product product, boolean vip) {
        Objects.requireNonNull(product, "product");

        long price = product.priceVnd();
        if (price < 0) {
            throw new IllegalArgumentException(
                    "priceVnd must not be negative");
        }

        if (vip && product.eligibleForVipDiscount()) {
            // Quy tắc ví dụ: giảm 10%, làm tròn xuống VND nguyên.
            return price - price / 10;
        }
        return price;
    }
}

final class PriceQuoteService {
    private final ProductReader products;
    private final DiscountPolicy discounts;

    PriceQuoteService(ProductReader products,
                      DiscountPolicy discounts) {
        this.products = Objects.requireNonNull(products, "products");
        this.discounts = Objects.requireNonNull(discounts, "discounts");
    }

    long quoteVnd(String sku, boolean vip) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        Product product = products.findBySku(sku);
        if (product == null) {
            throw new IllegalArgumentException("Unknown sku: " + sku);
        }

        return discounts.finalPriceVnd(product, vip);
    }
}
~~~

Trong ví dụ, `DiscountPolicy` không cần gọi ngược `PriceQuoteService` hay `ProductReader`. Chính sách chỉ biết dữ liệu đầu vào. Khi thay nguồn dữ liệu hoặc thêm cache, phần chính sách tính giá không cần biết chi tiết đó.

Hợp đồng `ProductReader` không tự động làm kiến trúc đúng. Nó có ích vì người dùng dữ liệu phụ thuộc vào **khả năng đọc sản phẩm**, còn việc triển khai kho dữ liệu chỉ cần thỏa hợp đồng. Nếu chỉ chuyển `CatalogService` sang một interface quá rộng ở cùng tầng mà giữ vòng package, chu kỳ có thể vẫn tồn tại.

### 7.4. Kiểm thử khi ranh giới rõ

Có thể kiểm thử chính sách độc lập với cơ sở dữ liệu:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountPolicyTest {
    private final DiscountPolicy policy = new DiscountPolicy();

    @Test
    void discountsEligibleVip() {
        Product product = new Product("P-01", 100_000L, true);
        assertEquals(90_000L, policy.finalPriceVnd(product, true));
    }

    @Test
    void keepsPriceForNonVip() {
        Product product = new Product("P-01", 100_000L, true);
        assertEquals(100_000L, policy.finalPriceVnd(product, false));
    }

    @Test
    void rejectsNegativePrice() {
        Product product = new Product("P-01", -1L, true);
        assertThrows(IllegalArgumentException.class,
                () -> policy.finalPriceVnd(product, true));
    }
}
~~~

Với `PriceQuoteService`, một stub nhỏ kiểm tra được đường điều phối:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PriceQuoteServiceTest {
    @Test
    void obtainsProductAndAppliesPolicy() {
        ProductReader reader = sku -> {
            if (!"P-01".equals(sku)) {
                return null;
            }
            return new Product("P-01", 200_000L, true);
        };

        PriceQuoteService service =
                new PriceQuoteService(reader, new DiscountPolicy());

        assertEquals(180_000L, service.quoteVnd("P-01", true));
        assertEquals(200_000L, service.quoteVnd("P-01", false));
    }
}
~~~

Lợi ích cụ thể:

- **Ít công dựng test:** không cần khởi tạo hai service đang tham chiếu vòng.
- **Test tập trung:** kiểm thử quy tắc giảm giá không phụ thuộc mạng, cơ sở dữ liệu hoặc container DI.
- **Đổi nguồn dữ liệu dễ hơn:** thay triển khai `ProductReader` mà không thay thuật toán giảm giá.
- **Review rõ hơn:** điều phối, đọc dữ liệu và tính toán có các hợp đồng riêng.

Tuy nhiên, unit test trên chỉ xác minh logic giả lập. Hệ thống thực vẫn cần kiểm thử tích hợp cho cách đọc sản phẩm, kiểm thử hợp đồng dữ liệu và quy định làm tròn/giá khi nghiệp vụ yêu cầu. **Phá chu kỳ không tự chứng minh hệ thống đúng**.

## 8. Các kỹ thuật tháo gỡ chu kỳ

### 8.1. Chuyển trách nhiệm điều phối lên một thành phần riêng

Khi A và B gọi qua lại để hoàn thành một workflow, đôi khi cần một **coordinator** hoặc application service gọi cả A lẫn B. Thay vì A → B → A, ta có Coordinator → A và Coordinator → B.

Phù hợp khi A và B có những trách nhiệm nghiệp vụ độc lập, còn trình tự kết hợp là trách nhiệm của luồng sử dụng.

**Đánh đổi:** coordinator có thể trở thành lớp quá lớn nếu gom mọi nghiệp vụ. Hãy giới hạn nó vào một use case hoặc nhóm workflow có liên quan.

### 8.2. Trích xuất khái niệm chung xuống thành phần ổn định

Nếu hai package import chéo chỉ để dùng chung một kiểu hoặc một quy tắc, cân nhắc đưa **khái niệm có sở hữu rõ ràng** vào module chung:

~~~text
Trước:
orders → payments
payments → orders

Sau, nếu cả hai thực sự dùng chung hợp đồng:
orders   → contracts
payments → contracts
~~~

Không nên tạo một package `common` chứa mọi thứ khó phân loại. Tách chung chỉ có giá trị khi đó là khái niệm ổn định, có hợp đồng rõ, không phụ thuộc ngược vào các bên sử dụng.

### 8.3. Phụ thuộc vào interface đúng tầng

**Dependency inversion** có thể giúp đảo hướng phụ thuộc: thành phần nghiệp vụ phụ thuộc vào một hợp đồng cần thiết, còn phần hạ tầng triển khai hợp đồng đó.

Ví dụ `PriceQuoteService → ProductReader ← DatabaseProductReader`. Giao diện nên đặt ở tầng mà chính sách phụ thuộc cho phép. Nếu A định nghĩa interface trong package B rồi B lại import các lớp nội bộ của A, vòng package vẫn còn; thêm interface chỉ để đổi tên chưa giải quyết vấn đề.

### 8.4. Truyền dữ liệu hoặc kết quả thay vì gọi ngược cả service

Trong ví dụ tính giá, `DiscountPolicy` chỉ cần `Product`, không cần cả `CatalogService`. Truyền đối tượng dữ liệu đã được xác thực có thể phá vòng và làm phạm vi phụ thuộc hẹp hơn.

Cần chú ý **quyền sở hữu dữ liệu** và tính bất biến. Truyền một đối tượng mutable dùng chung qua nhiều tầng có thể tạo phụ thuộc trạng thái dù biểu đồ import đã đẹp hơn.

### 8.5. Dùng sự kiện khi thực sự có nhu cầu tách thời gian xử lý

Một số workflow không cần lời gọi đồng bộ hai chiều. Thành phần A có thể phát sự kiện, B xử lý sau. Cách này có thể giảm phụ thuộc trực tiếp nhưng thêm các vấn đề khác: xử lý trùng, thứ tự, độ trễ nhất quán, retry, giám sát và đối soát.

**Không dùng event bus chỉ để làm sơ đồ không có vòng.** Nếu nghiệp vụ cần kết quả ngay hoặc một giao dịch nguyên tử, tách bất đồng bộ có thể làm yêu cầu khó đáp ứng hơn. Cần xác định hợp đồng và rủi ro trước.

### 8.6. Gộp lại nếu hai thành phần thật sự là một trách nhiệm

Đôi khi chu kỳ tồn tại vì nhóm đã chia một khái niệm gắn kết thành hai lớp hoặc package quá nhỏ. Nếu A và B luôn thay đổi cùng nhau, không có ranh giới hợp lý để kiểm thử độc lập, việc **gộp trách nhiệm** có thể đơn giản hơn việc thêm interface.

Không phải lúc nào “nhiều module hơn” cũng đồng nghĩa kiến trúc tốt hơn. Mục tiêu là ranh giới phản ánh ý nghĩa và nhu cầu thay đổi thực tế.

## 9. Phát hiện và đánh giá chu kỳ trong dự án

### 9.1. Từ biểu đồ phụ thuộc

Có thể mô hình hóa mã thành đồ thị có hướng:

- **Nút:** lớp, package, module hoặc service tùy cấp đánh giá.
- **Cạnh:** A phụ thuộc B theo định nghĩa đã chọn.
- **Chu kỳ:** đường có hướng quay lại điểm xuất phát.
- **Nhóm liên thông mạnh:** vùng có những thành phần phụ thuộc lẫn nhau; cần kiểm tra trách nhiệm bên trong.

Trước khi kết luận, phải xác định **đồ thị đang đo gì**. Phụ thuộc import tĩnh, lời gọi phương thức, bean injection, runtime HTTP, phụ thuộc test-only và phụ thuộc build có phạm vi khác nhau.

### 9.2. Công cụ và kiểm tra khả dĩ

Trong hệ Java, có thể sử dụng:

- **IDE:** xem sơ đồ package/module, tìm usages, import và những tham chiếu tạo vòng.
- **`jdeps`:** phân tích phụ thuộc tĩnh từ bytecode/artefact đã biên dịch; hỗ trợ xem quan hệ package/module, nhưng không bao quát mọi liên kết phản chiếu, cấu hình DI hoặc cuộc gọi mạng.
- **ArchUnit:** mô tả quy tắc kiến trúc bằng test, chẳng hạn yêu cầu các package/slice không có chu kỳ, tùy cấu trúc package và phiên bản thư viện.
- **Báo cáo build hoặc dependency graph:** kiểm tra chiều phụ thuộc giữa các module, tách phụ thuộc production khỏi test.
- **Tracing/quan sát runtime:** tìm chu trình lời gọi thực tế giữa các service; cần quan tâm cả luồng bất đồng bộ.

Một ví dụ quy tắc ArchUnit minh họa ý định (cần điều chỉnh pattern đúng package và cấu hình dự án):

~~~java
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;

final class ArchitectureRules {
    static void verifyNoPackageCycles() {
        JavaClasses classes = new ClassFileImporter()
                .importPackages("com.example");

        ArchRule rule = slices()
                .matching("com.example.(*)..")
                .should()
                .beFreeOfCycles();

        rule.check(classes);
    }
}
~~~

Ở đây, phần `(*)` nhóm package cấp đầu dưới `com.example`; nếu mã của bạn được tổ chức khác, cần chọn mẫu phù hợp. Việc chạy `rule.check(classes)` ở một bài kiểm thử kiến trúc hoặc bước CI giúp phát hiện chu kỳ mới ở cấp đã chọn.

**Giới hạn:** quy tắc dựa trên lớp được nạp và pattern đã chọn. Nếu bỏ sót module hoặc đặt các lớp trong một slice duy nhất, kết quả không phản ánh toàn bộ hệ thống. Cũng không nên biến thông báo công cụ thành kết luận tự động rằng mọi chu kỳ đều cần refactor ngay.

### 9.3. Cách ưu tiên xử lý

| Tiêu chí | Câu hỏi cần đánh giá |
| --- | --- |
| Kích thước nhóm phụ thuộc vòng | Vòng gồm hai lớp nhỏ hay hàng chục package nghiệp vụ? |
| Mức thay đổi | Các thành phần có được sửa thường xuyên và bởi nhiều nhóm không? |
| Tác động khi sai | Vòng nằm trên luồng thanh toán, quyền truy cập hoặc dữ liệu quan trọng? |
| Khó khăn khi kiểm thử | Có phải khởi tạo container, mock nhiều tầng hoặc test integration quá rộng không? |
| Khả năng tách phụ thuộc | Có hợp đồng hoặc trách nhiệm độc lập để chuyển hướng không? |
| Chi phí refactor | Thay đổi có ảnh hưởng API, dữ liệu lưu, thứ tự xử lý hoặc tương thích không? |

Một vòng nhỏ, ổn định và chủ đích trong mô hình đối tượng có thể ít ưu tiên hơn một vòng giữa nhiều package được thay đổi hàng tuần. Nên ghi lý do và điều kiện xem lại, thay vì dùng ngưỡng đếm chu kỳ như thước đo tuyệt đối.

## 10. Quy trình refactor chu kỳ an toàn

**Bước 1 — Chốt hành vi cần giữ.** Xác nhận yêu cầu, hợp đồng đầu vào/đầu ra, tác dụng phụ, ngoại lệ và thứ tự thao tác quan trọng. Viết kiểm thử hồi quy cho các luồng chính và trường hợp lỗi.

**Bước 2 — Vẽ vòng phụ thuộc nhỏ nhất.** Xác định cạnh nào tạo chu kỳ và vì sao mỗi thành phần cần cạnh đó. Phân biệt dùng dữ liệu, gọi nghiệp vụ, điều phối workflow và khởi tạo đối tượng.

**Bước 3 — Tìm trách nhiệm đặt sai chỗ.** Hỏi “vì sao B cần biết toàn bộ A?” và “B thực sự cần một giá trị, một hàm thuần, một hợp đồng nhỏ hay một workflow khác điều phối?”.

**Bước 4 — Chọn cách phá vòng ít thay đổi hành vi nhất.** Tách policy, truyền dữ liệu, thêm coordinator, di chuyển contract hoặc gộp lớp nếu cần. Tránh đổi đồng thời cấu trúc và quy tắc nghiệp vụ trừ khi thật sự bắt buộc.

**Bước 5 — Kiểm chứng ở đúng ranh giới.** Chạy unit test cho trách nhiệm thuần, integration/contract test cho phụ thuộc thực; kiểm tra việc khởi tạo đối tượng và các luồng có tác dụng phụ.

**Bước 6 — Xem lại đồ thị.** Xác nhận cạnh vòng đã biến mất **ở cấp cần giải quyết**. Nếu chỉ chuyển chu kỳ sang package hoặc module mới, việc refactor chưa đạt mục tiêu.

**Bước 7 — Ghi lại quyết định.** Nêu ranh giới mới, lý do, trade-off và quy tắc kiểm tra để tránh vòng tái xuất hiện. Có thể thêm architecture test hoặc quy ước chiều import.

Một thay đổi tốt nên vừa **giảm phụ thuộc hai chiều**, vừa giữ hành vi đúng và làm cách sửa đổi trong tương lai rõ hơn. Chỉ “chạy được container” hay “điểm công cụ chuyển sang xanh” là chưa đủ.

## 11. Những nhầm lẫn thường gặp

**“Có chu kỳ là chắc chắn xảy ra đệ quy vô hạn.”** Sai. Vòng tham chiếu kiểu dữ liệu và vòng gọi không kết thúc là hai hiện tượng khác nhau; cần xem luồng thực thi.

**“Chỉ cần thêm interface là phá được mọi chu kỳ.”** Sai. Nếu interface thuộc sai tầng hoặc các package vẫn tham chiếu chéo, vòng phụ thuộc kiến trúc còn tồn tại.

**“Dùng lazy injection làm hệ thống hết vòng.”** Không. Nó có thể thay đổi thời điểm tạo đối tượng hoặc cho phép khởi tạo, nhưng quan hệ phụ thuộc hai chiều vẫn cần được xem xét.

**“Không có chu kỳ build thì không có vấn đề.”** Không đúng. Chu kỳ class/package hoặc vòng gọi runtime có thể tồn tại dù các module build không phụ thuộc vòng.

**“Một lớp có nhiều phụ thuộc chắc chắn nằm trong chu kỳ.”** Không. Số cạnh đi ra cao (*fan-out*) khác với việc tồn tại đường quay lại chính lớp.

**“Cắt một lớp thành nhiều lớp sẽ giảm coupling.”** Chưa chắc. Nếu chỉ phân tán công việc nhưng vẫn import chéo, số cạnh phụ thuộc có thể còn tăng.

**“Phá chu kỳ đồng nghĩa có thể bỏ integration test.”** Không đúng. Hợp đồng và tương tác thực giữa các thành phần vẫn cần được kiểm chứng theo rủi ro.

**“Mọi phụ thuộc hai chiều đều là thiết kế sai.”** Cần ngữ cảnh. Tham chiếu cha–con hai chiều trong mô hình dữ liệu hoặc callback được quản lý rõ có thể hợp lý; vấn đề là chi phí hiểu, khởi tạo, thay đổi và kiểm thử mà nó gây ra.

## 12. Bài tập vận dụng

### Tình huống A — Vòng giữa hai package

Có đồ thị: `orders → payments → common → orders`. Nhóm định chuyển lớp `OrderStatus` từ `orders` sang `common`, nhưng `common` vẫn gọi `OrderService` để kiểm tra trạng thái.

**Câu hỏi:** chuyển `OrderStatus` có đủ phá vòng không?

**Gợi ý:** Chưa đủ nếu `common → orders` vẫn còn. Cần tìm lý do `common` gọi nghiệp vụ của `orders`: có thể chuyển việc điều phối lên tầng ứng dụng hoặc đưa một hợp đồng ổn định vào nơi phù hợp. Không biến `common` thành package có quyền biết mọi nghiệp vụ.

### Tình huống B — Test không dựng được service

`InvoiceService` cần `CustomerService`; `CustomerService` lại cần `InvoiceService` để tính hạng khách hàng. Kiểm thử đơn vị tính hạng phải tạo cả hai.

**Câu hỏi:** nên bắt đầu điều tra ở đâu?

**Gợi ý:** Xác định quy tắc tính hạng cần dữ liệu nào. Nếu chỉ cần tổng chi tiêu hoặc lịch sử hóa đơn, cân nhắc cung cấp dữ liệu qua một hợp đồng đọc hẹp hoặc để application service điều phối rồi truyền dữ liệu vào một policy thuần. Kiểm thử policy bằng dữ liệu mẫu mà không phải dựng cả vòng service.

### Tình huống C — Vòng HTTP giữa các dịch vụ

Dịch vụ A gọi B để xác minh đơn; B gọi A để lấy thêm thông tin đơn trong cùng yêu cầu. Khi A chậm, cả hai tăng thời gian chờ và số luồng bị chiếm.

**Câu hỏi:** chỉ bỏ import chéo trong Java có giải quyết được không?

**Gợi ý:** Không. Cần xét sơ đồ runtime: truyền đủ dữ liệu ở một chiều, định nghĩa hợp đồng chuyên biệt, giới hạn deadline, tránh gọi vòng trong cùng workflow hoặc chuyển trách nhiệm phối hợp về thành phần phù hợp. Khi sửa phải kiểm chứng cả trường hợp timeout và kết quả nghiệp vụ.

### Tình huống D — Giữ lại một chu kỳ có chủ đích

Một cấu trúc `TreeNode` có tham chiếu đến `parent` và danh sách `children`. Người đọc dễ hiểu, test đơn giản và thay đổi ít.

**Câu hỏi:** có nhất thiết phải loại hết tham chiếu hai chiều?

**Gợi ý:** Không nhất thiết. Cần kiểm soát bất biến khi gắn/tách nút, cách duyệt tránh lặp vô hạn, và quy tắc sở hữu trạng thái. Mục tiêu là an toàn và dễ bảo trì, không phải xóa mọi mũi tên quay lại trong tất cả mô hình.

## 13. Checklist khi review cấu trúc và phụ thuộc

Trước một chu kỳ được công cụ cảnh báo, hãy hỏi:

1. **Đồ thị ở cấp nào?** Class, package, module, đối tượng lúc khởi tạo hay service runtime?
2. **Vòng chính xác là gì?** Có thể chỉ rõ đường A → B → … → A không?
3. **Trách nhiệm nào làm vòng hình thành?** Dùng dữ liệu, điều phối, tính toán, callback hay phụ thuộc kỹ thuật?
4. **Vòng gây hậu quả gì?** Khó setup test, lan truyền thay đổi, khởi tạo lỗi, khó deploy hay chỉ là cảnh báo ít tác động?
5. **Phương án phá vòng nào phù hợp nhất?** Tách dữ liệu, policy, contract, coordinator, sự kiện hay gộp trách nhiệm?
6. **Đã giữ đúng hành vi chưa?** Có test cho quy tắc, lỗi, tác dụng phụ và tương thích cần thiết?
7. **Đã phá ở đúng cấp chưa?** Chu kỳ có bị chuyển sang module/package khác không?
8. **Làm sao ngăn tái phát?** Có quy ước chiều phụ thuộc, kiến trúc được ghi nhận và kiểm tra phù hợp không?

Chu kỳ phụ thuộc là tín hiệu quan trọng vì nó làm mờ ranh giới giữa các trách nhiệm. Xử lý đúng giúp **kiểm thử dễ cô lập hơn, thay đổi ít lan truyền hơn và luồng xử lý dễ hiểu hơn**. Trong **CODE_QUALITY_FUNDAMENTALS**, mục tiêu không chỉ là loại một cạnh vòng trên sơ đồ mà là xây dựng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi** dựa trên trách nhiệm và hợp đồng thực tế.
