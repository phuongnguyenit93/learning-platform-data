# Dùng fake, stub hoặc mock qua interface trong Java

## 1. Vì sao dùng interface trong kiểm thử?

Một lớp thường cần cộng tác với một thành phần bên ngoài: repository, cổng thanh toán, dịch vụ gửi thông báo, đồng hồ hệ thống hoặc API từ xa. Nếu lớp nghiệp vụ tự tạo trực tiếp một triển khai cụ thể bên trong phương thức, việc thay thế thành phần đó khi kiểm thử sẽ khó hơn.

Interface tạo ra một hợp đồng nhỏ giữa bên sử dụng và bên cung cấp. Lớp nghiệp vụ phụ thuộc vào hợp đồng, không phụ thuộc vào một lớp triển khai cụ thể. Khi chạy ứng dụng, có thể truyền implementation thật; trong kiểm thử, có thể truyền một test double phù hợp với mục tiêu của bài test.

**Test double** là tên gọi chung cho đối tượng thay thế một dependency thật trong kiểm thử. Fake, stub và mock đều là các loại test double, nhưng chúng được dùng với mục đích khác nhau:

- **Stub** trả về câu trả lời đã định trước để kiểm soát tình huống đầu vào và tập trung kiểm tra kết quả của mã đang được test.
- **Fake** là một triển khai đơn giản nhưng có hoạt động thực tế. Ví dụ thường gặp là repository lưu dữ liệu trong bộ nhớ thay vì cơ sở dữ liệu thật.
- **Mock** tập trung vào việc ghi nhận hoặc xác minh tương tác: phương thức nào được gọi, với đối số nào, bao nhiêu lần hoặc theo thứ tự nào. Framework mocking có thể tự động cấu hình và xác minh các kỳ vọng đó.
- **Spy** là một lựa chọn liên quan: nó ghi nhận tương tác, thường bằng cách bọc một triển khai khác và có thể cho lời gọi tiếp tục chạy hành vi thật.

Cách gọi có thể khác đôi chút giữa các nhóm phát triển và framework. Điểm quan trọng là chọn test double dựa trên điều cần chứng minh, không chỉ dựa vào tên gọi.

## 2. Thiết kế một điểm thay thế qua interface

Ví dụ này có một interface tên **PriceCatalog**, cung cấp giá sản phẩm theo mã. **CheckoutService** nhận interface đó qua constructor và dùng nó để tính tổng giá. Lớp nghiệp vụ không cần biết giá đến từ bản đồ trong bộ nhớ, một stub, một mock hay dịch vụ thật.

Mối quan hệ có thể hình dung như sau:

~~~text
Test hoặc ứng dụng
        |
        v
  CheckoutService
        |
        v
   PriceCatalog
    /    |     \
   v     v      v
  Stub  Fake   Mock
~~~

Đây là dependency injection qua constructor: dependency được truyền từ bên ngoài thay vì được tạo cứng bên trong **CheckoutService**. Vì **PriceCatalog** chỉ có một phương thức trừu tượng, nó cũng là một functional interface và có thể được triển khai bằng lambda khi phù hợp.

## 3. Ví dụ hoàn chỉnh với Java 17+

Ví dụ chạy độc lập, không cần thư viện kiểm thử bên ngoài. Chương trình dùng cùng một **CheckoutService** với ba test double khác nhau: stub, fake và mock ghi nhận lời gọi.

Tạo file **Main.java** với nội dung sau:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class Main {
    @FunctionalInterface
    interface PriceCatalog {
        int priceInCents(String sku);
    }

    static final class CheckoutService {
        private final PriceCatalog catalog;

        CheckoutService(PriceCatalog catalog) {
            this.catalog = Objects.requireNonNull(catalog, "catalog");
        }

        int totalInCents(String sku, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            int unitPrice = catalog.priceInCents(sku);
            if (unitPrice < 0) {
                throw new IllegalStateException("price must not be negative");
            }
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    // Stub: always returns a predetermined price.
    static final class StubPriceCatalog implements PriceCatalog {
        private final int fixedPrice;

        StubPriceCatalog(int fixedPrice) {
            if (fixedPrice < 0) {
                throw new IllegalArgumentException("price must not be negative");
            }
            this.fixedPrice = fixedPrice;
        }

        @Override
        public int priceInCents(String sku) {
            return fixedPrice;
        }
    }

    // Fake: a small, working in-memory catalog.
    static final class FakePriceCatalog implements PriceCatalog {
        private final Map<String, Integer> prices;

        FakePriceCatalog(Map<String, Integer> prices) {
            this.prices = Map.copyOf(prices);
        }

        @Override
        public int priceInCents(String sku) {
            Integer price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            return price;
        }
    }

    // Mock: returns a controlled value and records interactions for verification.
    static final class MockPriceCatalog implements PriceCatalog {
        private final int fixedPrice;
        private final List<String> requestedSkus = new ArrayList<>();

        MockPriceCatalog(int fixedPrice) {
            if (fixedPrice < 0) {
                throw new IllegalArgumentException("price must not be negative");
            }
            this.fixedPrice = fixedPrice;
        }

        @Override
        public int priceInCents(String sku) {
            requestedSkus.add(sku);
            return fixedPrice;
        }

        List<String> requestedSkus() {
            return List.copyOf(requestedSkus);
        }
    }

    public static void main(String[] args) {
        CheckoutService stubService =
                new CheckoutService(new StubPriceCatalog(250));
        int stubTotal = stubService.totalInCents("BOOK", 3);
        if (stubTotal != 750) {
            throw new AssertionError("Unexpected stub total: " + stubTotal);
        }

        FakePriceCatalog fakeCatalog = new FakePriceCatalog(
                Map.of("BOOK", 250, "PEN", 75));
        CheckoutService fakeService = new CheckoutService(fakeCatalog);
        int fakeTotal = fakeService.totalInCents("BOOK", 2)
                + fakeService.totalInCents("PEN", 1);
        if (fakeTotal != 575) {
            throw new AssertionError("Unexpected fake total: " + fakeTotal);
        }

        MockPriceCatalog mockCatalog = new MockPriceCatalog(250);
        CheckoutService mockService = new CheckoutService(mockCatalog);
        int mockTotal = mockService.totalInCents("BOOK", 2);
        if (mockTotal != 500
                || !mockCatalog.requestedSkus().equals(List.of("BOOK"))) {
            throw new AssertionError("Unexpected mock interaction");
        }

        System.out.println("Stub total: " + stubTotal + " cents");
        System.out.println("Fake total: " + fakeTotal + " cents");
        System.out.println("Mock total: " + mockTotal + " cents");
        System.out.println("Mock calls: " + mockCatalog.requestedSkus());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~text
javac Main.java
java Main
~~~

Stdout chính xác:

~~~text
Stub total: 750 cents
Fake total: 575 cents
Mock total: 500 cents
Mock calls: [BOOK]
~~~

Nếu có lỗi biên dịch hoặc một điều kiện kiểm tra không đạt, chương trình sẽ kết thúc với lỗi thay vì âm thầm in kết quả thành công.

## 4. Đọc từng test double trong ví dụ

### Stub: kiểm soát câu trả lời

**StubPriceCatalog** luôn trả về giá đã cấu hình khi khởi tạo. Trong ví dụ, giá được đặt là 250 xu, nên mua ba đơn vị cho kết quả 750 xu. Mục tiêu là kiểm tra phép tính của **CheckoutService** mà không phụ thuộc vào dữ liệu bên ngoài.

Stub đặc biệt hữu ích khi cần mô phỏng tình huống cụ thể, chẳng hạn giá bằng 0, bản ghi không tồn tại, một kết quả rỗng hoặc lỗi từ dependency. Hãy thiết kế stub để biểu đạt rõ tình huống đang kiểm tra; tránh biến nó thành một hệ thống mô phỏng quá phức tạp.

### Fake: hành vi đơn giản nhưng có thật

**FakePriceCatalog** lưu giá trong một **Map**. Nó thực hiện tra cứu theo mã sản phẩm và báo lỗi khi mã không có trong danh mục. Đây là một triển khai hoạt động thực tế nhưng đơn giản hơn hệ thống thật, vì không cần kết nối cơ sở dữ liệu hoặc dịch vụ từ xa.

Fake hữu ích khi cần kiểm thử nhiều tương tác với dữ liệu có cấu trúc mà không muốn phụ thuộc vào hạ tầng. Ví dụ khác gồm repository trong bộ nhớ, hàng đợi đơn giản hoặc filesystem giả lập. Fake cần giữ các quy tắc quan trọng mà bài test dựa vào; nếu hành vi của fake quá khác hệ thống thật, test có thể tạo cảm giác an toàn sai.

### Mock: kiểm tra tương tác

**MockPriceCatalog** vừa trả về giá cố định vừa ghi lại mã sản phẩm được yêu cầu. Bài kiểm tra xác minh hai điều: tổng giá là 500 xu và danh sách lời gọi đúng bằng **["BOOK"]**.

Điểm khác biệt không nằm ở việc mock có trả về giá hay không; nó nằm ở việc bài test chủ động xác minh tương tác. Trong dự án thực tế, mock có thể giúp kiểm tra một cổng thanh toán được gọi đúng một lần, một thông báo được gửi tới đúng người nhận hoặc một dependency được gọi với đúng đối số.

Mock viết tay trong ví dụ chỉ ghi nhận lời gọi đơn giản. Nó minh họa ý tưởng, không thay thế đầy đủ tính năng của các framework mocking như cấu hình kỳ vọng, xác minh số lần gọi, thứ tự gọi hoặc mô phỏng ngoại lệ.

## 5. Chọn đúng loại theo mục tiêu kiểm thử

| Điều muốn kiểm tra | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Công thức tính tổng với một giá đã biết | Stub | Kết quả đầu vào được kiểm soát |
| Luồng xử lý trên một tập dữ liệu nhỏ, nhất quán | Fake | Có hành vi đủ thực tế mà không cần hạ tầng |
| Một dependency phải được gọi đúng đối số hoặc số lần | Mock | Tương tác là một phần của hợp đồng cần kiểm chứng |
| Tích hợp với database, mạng hoặc dịch vụ thật | Integration test với dependency thật hoặc môi trường kiểm thử chuyên dụng | Test double không chứng minh rằng tích hợp thật hoạt động đúng |

Không cần mock mọi dependency. Nếu bài test chỉ quan tâm đầu ra, stub hoặc fake thường đơn giản và dễ đọc hơn. Mock đặc biệt hữu ích khi tương tác với dependency chính là hành vi cần kiểm tra, nhưng xác minh quá nhiều lời gọi nội bộ có thể khiến test giòn: một thay đổi triển khai không ảnh hưởng kết quả vẫn làm test thất bại.

## 6. Interface và dependency injection: các nguyên tắc thiết kế

- **Định nghĩa hợp đồng theo nhu cầu của bên sử dụng.** Interface nên nhỏ và biểu đạt khả năng cần thiết, không sao chép toàn bộ API của hệ thống bên ngoài.
- **Truyền dependency qua constructor.** Việc thay thế implementation trở nên rõ ràng, và đối tượng có thể giữ dependency trong trường **private final**.
- **Giữ test double bên ngoài logic nghiệp vụ.** **CheckoutService** chỉ gọi **PriceCatalog**; nó không cần **if** để phân biệt đang chạy với stub, fake, mock hay implementation thật.
- **Tách phần có tác dụng phụ.** Truy cập mạng, thời gian hệ thống, tệp và database thường là các ranh giới hữu ích để đưa ra interface khi việc thay thế giúp kiểm thử rõ ràng hơn.
- **Không tạo interface cho mọi lớp theo máy móc.** Nếu một lớp nhỏ không có nhu cầu thay thế, không nằm ở ranh giới quan trọng và không cần một hợp đồng độc lập, thêm interface có thể chỉ tăng độ phức tạp.
- **Tránh trạng thái dùng chung giữa các test.** Mỗi test nên tạo test double mới hoặc reset trạng thái một cách tường minh, để thứ tự chạy test không ảnh hưởng kết quả.
- **Xác minh hành vi có ý nghĩa.** Ưu tiên kết quả và các tương tác thuộc hợp đồng; đừng khóa test vào chi tiết triển khai không quan trọng.

Dependency injection không bắt buộc phải dùng framework. Trong ví dụ, việc tạo **CheckoutService** với một **StubPriceCatalog** đã là injection qua constructor. Một ứng dụng lớn có thể dùng container để lắp ráp dependency, nhưng nguyên tắc thiết kế vẫn giống nhau.

## 7. Giới hạn của test doubles

Test double giúp kiểm tra logic một cách nhanh chóng và có kiểm soát, nhưng không chứng minh rằng dependency thật hoạt động đúng. Một fake có thể không mô phỏng hết giao dịch, khóa đồng thời hoặc ràng buộc của database; một stub có thể bỏ qua các lỗi thực tế của API; một mock có thể xác minh lời gọi nhưng không xác minh rằng dịch vụ từ xa thực sự xử lý yêu cầu đúng.

Vì vậy, hãy kết hợp các mức kiểm thử phù hợp:

1. **Unit test:** kiểm tra logic của một đơn vị bằng stub, fake hoặc mock khi hữu ích.
2. **Integration test:** xác minh những thành phần quan trọng thực sự làm việc cùng nhau, chẳng hạn repository với database kiểm thử.
3. **Contract test hoặc kiểm thử đầu-cuối:** khi cần, xác minh hợp đồng giữa các hệ thống hoặc luồng nghiệp vụ hoàn chỉnh.

Không phải dự án nào cũng cần tất cả các mức ở cùng độ sâu. Chọn dựa trên rủi ro, chi phí và các lỗi mà mỗi mức có thể phát hiện.

## 8. Lỗi thường gặp

- **Gọi mọi test double là mock.** Hãy phân biệt mục tiêu: trả kết quả định trước, mô phỏng hành vi thực tế đơn giản hay xác minh tương tác.
- **Mock quá sâu vào chi tiết nội bộ.** Test dễ hỏng khi tái cấu trúc dù hành vi bên ngoài không thay đổi.
- **Fake không giống hợp đồng thật.** Khi cần thiết, giữ một bộ test hợp đồng để cùng xác minh fake và implementation thật.
- **Dùng test double rồi cho rằng đã kiểm tra tích hợp.** Stub không kiểm tra mạng, database, cấu hình hoặc quyền truy cập thật.
- **Để test double rò rỉ vào mã production.** Mã nghiệp vụ nên phụ thuộc vào interface; việc lựa chọn implementation thường thuộc lớp khởi tạo ứng dụng hoặc cấu hình test.
- **Chia sẻ mock có trạng thái giữa nhiều test.** Lịch sử lời gọi cũ có thể khiến kết quả phụ thuộc thứ tự chạy.
- **Kiểm tra tương tác không mang ý nghĩa nghiệp vụ.** Chỉ xác minh lời gọi khi việc gọi đó là một phần của yêu cầu, không phải chỉ vì có thể ghi nhận nó.

## 9. Checklist trước khi chọn test double

1. Điều quan trọng nhất của test là kết quả trả về, hành vi trên dữ liệu hay tương tác với dependency?
2. Có thể dùng stub đơn giản để cô lập tình huống không?
3. Một fake nhỏ có làm test dễ hiểu hơn và đủ gần với hợp đồng cần dùng không?
4. Có thật sự cần xác minh đối số, số lần gọi hoặc thứ tự tương tác để dùng mock không?
5. Các integration test cần thiết có bao phủ những khác biệt mà test double không mô phỏng được không?
6. Interface có tạo ra một ranh giới hữu ích, hay chỉ thêm một lớp trừu tượng không cần thiết?

Tóm lại, interface giúp mã nghiệp vụ phụ thuộc vào hợp đồng có thể thay thế. Stub kiểm soát câu trả lời, fake cung cấp một triển khai giản lược nhưng hoạt động, còn mock giúp xác minh tương tác. Chọn loại đơn giản nhất có thể chứng minh yêu cầu của bài test, và đừng nhầm unit test thành bằng chứng cho toàn bộ hệ thống tích hợp.