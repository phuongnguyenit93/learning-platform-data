# Độ gắn kết bên trong một đơn vị mã

> **Chương:** Cấu trúc và phụ thuộc  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **độ gắn kết (cohesion)** là gì ở cấp phương thức, lớp và module, và vì sao nó ảnh hưởng đến khả năng hiểu, kiểm tra, thay đổi mã.
2. Nhận diện khi những phần bên trong một đơn vị mã phục vụ **một mục đích chung** hoặc đang bị gom lại do tiện tay, tên gọi chung chung hay vị trí trong dự án.
3. Phân biệt **cohesion** với **coupling (mức phụ thuộc giữa các đơn vị)**, tránh coi chúng là cùng một chỉ số.
4. Phân tích một ví dụ Java có trách nhiệm pha trộn, đề xuất ranh giới mới và chỉ ra tác dụng phụ, lợi ích, chi phí của việc tách.
5. Dùng câu hỏi về hành vi, lý do thay đổi, bất biến dữ liệu và kiểm thử để đánh giá độ gắn kết, thay vì chỉ dựa vào số dòng hoặc số phương thức.

## 1. Độ gắn kết trả lời câu hỏi gì?

Hãy xem một lớp tên `CustomerManager` có các phương thức: tính tiền đơn hàng, xuất báo cáo khách hàng ra CSV, gửi email chào mừng và đổi địa chỉ giao hàng. Tất cả đều “liên quan đến khách hàng”, nhưng khi yêu cầu thay đổi định dạng CSV thì phép tính giá, nội dung email và quy tắc địa chỉ không có lý do gì phải thay đổi theo.

Ngược lại, một lớp `OrderPricing` có các thao tác kiểm tra dòng hàng, tính tổng trước ưu đãi và áp dụng chính sách giảm giá. Những thao tác này cùng hỗ trợ **một trách nhiệm rõ ràng**: xác định số tiền cần thanh toán theo quy tắc đã cho.

**Độ gắn kết bên trong một đơn vị mã** mô tả mức độ các thành phần của đơn vị ấy **liên hệ với nhau để thực hiện một trách nhiệm có ý nghĩa**. Thành phần có thể là các câu lệnh trong phương thức, các phương thức/trường dữ liệu trong lớp hoặc các lớp trong module.

Một đơn vị có độ gắn kết phù hợp thường dễ trả lời:

- Nó tồn tại để làm **việc gì**?
- Mỗi phần bên trong đóng góp thế nào cho công việc đó?
- Những **quy tắc, dữ liệu, bất biến** nào nó chịu trách nhiệm bảo vệ?
- Khi có một thay đổi nghiệp vụ cụ thể, phần nào trong đơn vị cần thay đổi cùng nhau?

Độ gắn kết **không đồng nghĩa với ít mã**. Một thuật toán dài nhưng có một mục tiêu nhất quán có thể gắn kết hơn một lớp ngắn chứa ba việc độc lập. Nó cũng không đồng nghĩa với việc mọi phương thức trong lớp phải truy cập cùng một biến.

### Liên hệ với chất lượng mã nguồn

| Khía cạnh chất lượng | Khi độ gắn kết hợp lý | Khi trách nhiệm bị pha trộn |
| --- | --- | --- |
| Dễ hiểu | Người đọc xác định được mục đích và quy tắc của đơn vị | Phải giữ trong đầu nhiều mối quan tâm không liên quan |
| Dễ thay đổi | Sửa quy tắc thường tập trung ở vùng có trách nhiệm rõ | Sửa một việc dễ đụng mã của nhiều việc khác |
| Dễ kiểm tra | Bài kiểm thử có phạm vi và điều kiện đầu vào rõ | Phải thiết lập các phụ thuộc không liên quan để thử một hành vi |
| Đáng tin cậy | Bất biến và ranh giới tác dụng phụ dễ nhận biết | Trạng thái dùng chung ngoài nhu cầu có thể gây ảnh hưởng chéo |
| Dễ tái sử dụng | Đơn vị có hợp đồng đủ rõ để dùng trong đúng ngữ cảnh | Người dùng bị buộc kéo theo những hành vi hoặc phụ thuộc thừa |

Đây là xu hướng thiết kế, không phải bảo đảm tuyệt đối: hai đơn vị tách biệt vẫn có thể phụ thuộc chặt vào nhau, làm hệ thống khó sửa.

## 2. Đánh giá độ gắn kết ở đúng cấp độ

### 2.1. Bên trong một phương thức

Hãy hỏi: *Tất cả các bước có cần thiết để hoàn thành một hành vi được đặt tên rõ không?*

Một phương thức tính thuế, làm tròn và cộng vào tổng có thể rất gắn kết vì tất cả các bước phục vụ **tính số tiền sau thuế**. Nếu phương thức còn đổi mật khẩu người dùng và dọn file log định kỳ, những bước đó khó giải thích bằng cùng một mục tiêu.

Phương thức có nhiều bước **không tự động** là có độ gắn kết thấp. Một quy trình đặt hàng có thể cần xác thực, tính giá, gửi thanh toán và lưu đơn; nếu phương thức thực sự đóng vai trò **điều phối ca sử dụng (use case)**, các bước liên tiếp vẫn có thể phục vụ một mục tiêu chung. Điều cần xem là nó có đang tự đảm nhiệm chi tiết của nhiều quy tắc không liên quan hay chỉ điều phối các thành phần có trách nhiệm riêng.

### 2.2. Bên trong một lớp

Hãy hỏi: *Các trường và phương thức có cùng bảo vệ một khái niệm hoặc một nhóm bất biến không?*

Ví dụ, `BankAccount` có `deposit`, `withdraw` và `balance`: ba hành vi cùng duy trì bất biến “số dư không được âm” nếu hợp đồng quy định như vậy. Giữ chúng gần nhau làm rõ nơi kiểm soát thay đổi số dư.

Một lớp `Utilities` chứa mã hóa URL, tính thuế và gửi email không thể giải thích bằng một khái niệm chung đủ cụ thể. Tên “tiện ích” chỉ nói về **cách gom mã**, chưa nói về trách nhiệm.

Không phải lớp chỉ có một phương thức mới là “đúng”. Một lớp gắn kết có thể có nhiều phương thức phụ trợ để giữ đúng bất biến; ngược lại một lớp chỉ có một phương thức rất dài vẫn có thể ôm nhiều trách nhiệm.

### 2.3. Bên trong một module hoặc package

Hãy hỏi: *Những kiểu dữ liệu và dịch vụ ở đây cùng phục vụ năng lực nghiệp vụ hoặc trách nhiệm kỹ thuật nào?*

Module `billing` chứa quy tắc hóa đơn, chính sách thanh toán và các cổng tích hợp liên quan có thể gắn kết theo năng lực thanh toán. Package `common` chứa mọi thứ không biết đặt đâu thường khó xác định chủ sở hữu và ranh giới thay đổi.

Tuy nhiên, module không nhất thiết chỉ chứa một lớp hay một loại thao tác. Một module chức năng có thể bao gồm API, domain model, persistence adapter và test; mức gắn kết cần đánh giá theo **mục tiêu của module**, không chỉ theo sự tương đồng cú pháp giữa các lớp.

### 2.4. Độ gắn kết phụ thuộc vào cách đặt tên và mức trừu tượng

Mục đích “xử lý mọi thứ liên quan tới hệ thống” quá rộng để giúp phân ranh. Mục đích “tính tổng phải trả cho một đơn hàng bằng VND” đủ cụ thể để biết code nào phù hợp.

Cùng đoạn mã có thể nhìn khác nhau ở các mức:

~~~text
Module: Đặt hàng
  ├─ CheckoutUseCase: điều phối hoàn tất đặt hàng
  │    ├─ PricingPolicy: tính giá theo chính sách
  │    ├─ PaymentPort: gửi yêu cầu thanh toán
  │    └─ OrderStore: lưu trạng thái đơn
  └─ OrderQuery: đọc đơn hàng cho khách hàng
~~~

`CheckoutUseCase` có thể gắn kết ở cấp **quy trình đặt hàng**, dù bên trong gọi nhiều dịch vụ. `PricingPolicy` có thể gắn kết ở cấp **quy tắc tính giá**. Không nên yêu cầu cả hai phải làm cùng một loại việc; mỗi đơn vị được đánh giá theo hợp đồng của chính nó.

## 3. Những kiểu gắn kết thường gặp

Một số tài liệu thiết kế phần mềm phân biệt các dạng cohesion để giải thích cách hoạt động được gom lại. Có thể dùng chúng như **khung phân tích**, không coi là bảng chấm điểm cơ học hoặc thứ tự cố định cho mọi kiến trúc.

| Dạng | Cách các phần liên hệ | Ví dụ | Điều cần xem xét |
| --- | --- | --- | --- |
| **Trùng hợp (coincidental)** | Không có quan hệ chức năng rõ; chỉ được đặt cạnh nhau | `MiscUtils` vừa tính thuế vừa format CSV | Thường khó tìm lý do hợp lý để cùng thay đổi |
| **Theo loại thao tác (logical)** | Chỉ giống loại công việc kỹ thuật | Một hàm `handle(mode)` xử lý in, lưu, gửi email theo cờ | Có thể chứa nhiều đường đi độc lập và hợp đồng khó đọc |
| **Theo thời điểm (temporal)** | Chạy cùng lúc, ví dụ khi khởi động/đóng ứng dụng | `initializeEverything()` cấu hình cache, email, database | Có thể gắn kết ở cấp điều phối lifecycle; phần triển khai chi tiết vẫn nên có chủ sở hữu rõ |
| **Theo trình tự (procedural)** | Được gọi theo một thứ tự chung | Kiểm tra session, ghi audit, dọn cache trong một chuỗi không cùng mục đích | Thứ tự thực thi chưa đủ chứng minh cùng trách nhiệm |
| **Theo dữ liệu (communicational)** | Dùng chung một bộ dữ liệu | Các hàm đọc/sửa thông tin một đơn hàng | Cần hỏi có cùng bảo vệ một khái niệm/bất biến hay chỉ cùng nhận một object lớn |
| **Theo luồng dữ liệu (sequential)** | Đầu ra bước trước là đầu vào bước sau | Parse → kiểm tra → chuẩn hóa một mã định danh | Thường có mục tiêu rõ, nhưng có thể tách nếu bước có lý do thay đổi độc lập |
| **Theo chức năng (functional)** | Mọi phần cùng hướng tới một kết quả/trách nhiệm xác định | Kiểm tra dòng hàng → tính tổng → áp dụng giảm giá | Thường giúp hiểu và kiểm chứng hành vi dễ hơn |

Những dạng này có thể cùng xuất hiện. Ví dụ một phương thức xử lý yêu cầu vừa theo trình tự, vừa theo chức năng. Một bootstrapper điều phối nhiều thành phần lúc khởi động có thể là thiết kế tốt; gọi nó là “temporal cohesion” không tự động biến nó thành lỗi.

Cách hỏi hữu ích hơn tên loại là: **“Nếu bỏ bước này ra, trách nhiệm đã đặt tên có còn được thực hiện đầy đủ và nhất quán không?”** Sau đó hỏi tiếp bước này có chủ sở hữu khác phù hợp hơn hay không.

## 4. Phân biệt cohesion với coupling

Hai thuộc tính liên quan nhưng không trùng nhau:

- **Cohesion (độ gắn kết)** nhìn **vào bên trong một đơn vị**: những thành phần có phục vụ mục tiêu chung không?
- **Coupling (mức liên kết/phụ thuộc)** nhìn **giữa các đơn vị**: chúng cần biết và dựa vào nhau nhiều đến đâu?

~~~mermaid
flowchart LR
    subgraph P["PricingPolicy — nội bộ cùng trách nhiệm tính giá"]
        A["Kiểm tra dòng hàng"] --> B["Tính tổng"]
        B --> C["Áp dụng ưu đãi"]
    end
    X["CheckoutUseCase"] -->|"gọi qua hợp đồng"| P
    X -->|"gửi yêu cầu"| Y["PaymentPort"]
    X -->|"lưu đơn"| Z["OrderStore"]
~~~

Trong ví dụ trên, `PricingPolicy` được đánh giá về gắn kết giữa kiểm tra dữ liệu và tính giá; quan hệ từ `CheckoutUseCase` tới `PricingPolicy` là một **phụ thuộc giữa đơn vị**.

Một thiết kế có thể **gắn kết cao nhưng vẫn coupling cao** nếu lớp tính giá truy cập trực tiếp hàng chục bảng và cấu hình bên ngoài. Ngược lại, một lớp rất ít phụ thuộc nhưng chứa nhiều hàm hoàn toàn không liên quan có thể coupling thấp mà cohesion thấp.

Tách một “god class” thành nhiều lớp không tự bảo đảm chất lượng nếu các lớp mới trao đổi trạng thái nội bộ liên tục, gọi nhau vòng vo hoặc buộc sửa đồng thời mỗi khi đổi một chính sách. Khi đề xuất tách, phải đánh giá cả **mục đích bên trong** và **ranh giới phụ thuộc mới**.

## 5. Dấu hiệu một đơn vị mã có độ gắn kết yếu

### 5.1. Có nhiều lý do thay đổi độc lập

Một yêu cầu sửa quy tắc giảm giá, một yêu cầu đổi mẫu email và một yêu cầu đổi schema CSV đều buộc sửa cùng lớp `CustomerManager`. Các thay đổi này đến từ **ba nguồn quyết định khác nhau**.

Câu hỏi review:

> “Nếu tuần tới chỉ một trong các chính sách thay đổi, các thành phần còn lại trong lớp có lý do gì phải xem xét theo không?”

Đây là cách áp dụng thực dụng nguyên lý *Single Responsibility*: chú ý **lý do thay đổi độc lập** thay vì giải thích cứng rằng “mỗi lớp chỉ được có một phương thức”.

### 5.2. Tên rất rộng và hành vi khó tóm tắt

Tên `Manager`, `Handler`, `Helper`, `Common` không tự động sai. Nhưng khi phải diễn giải “lớp này làm A, và B, và C không liên quan”, đó là tín hiệu cần kiểm tra.

Đặt một tên thật chung cho nhiều nhiệm vụ không tạo ra gắn kết; nó chỉ che việc chưa xác định ranh giới.

### 5.3. Có nhóm trường/phương thức không tương tác về nghiệp vụ

Ví dụ lớp chứa các trường `smtpClient`, `csvEncoder`, `discountRate`. Hàm gửi email chỉ dùng `smtpClient`, hàm xuất dữ liệu chỉ dùng `csvEncoder`, hàm tính giá chỉ dùng `discountRate`. Mỗi nhóm phát triển độc lập và không chia sẻ một bất biến. Sự tách nhóm này là tín hiệu lớp đang bao nhiều trách nhiệm.

Tuy vậy, **không truy cập cùng một field** không đồng nghĩa chắc chắn thiếu gắn kết: lớp điều phối stateless có thể ít field mà vẫn thực hiện một use case rõ ràng.

### 5.4. Khi kiểm thử một hành vi phải dựng phụ thuộc không liên quan

Chỉ muốn xác nhận giá sau giảm mà test phải khởi động SMTP, database và trình xuất Excel, có thể hàm hoặc constructor đang gộp nhiều hành vi. Nếu mỗi test phải cấu hình rất nhiều mock mà phần lớn không liên quan, nên đánh giá lại thiết kế.

Số lượng mock chỉ là tín hiệu, không phải bằng chứng tuyệt đối: một integration test cần nhiều thành phần có thể hoàn toàn hợp lý để xác nhận luồng tổng thể.

### 5.5. Các câu lệnh chia thành nhiều cụm khó giải thích bằng một mục tiêu

Một phương thức đang tính tổng hàng thì đột nhiên dọn cache không liên quan rồi gửi newsletter. Sự chuyển chủ đề bất ngờ khiến người đọc phải đổi mô hình tinh thần.

Cần phân biệt với luồng nghiệp vụ hợp lệ: “tính tiền rồi lưu đơn rồi gửi xác nhận” có thể là một **chuỗi phối hợp của use case**. Điều đáng ngờ là logic chi tiết của ba trách nhiệm đều được nhồi vào cùng phương thức thay vì được diễn đạt bằng các lời gọi có hợp đồng rõ.

## 6. Ví dụ Java: một lớp chứa các trách nhiệm không liên quan

Giả sử hệ thống có ba yêu cầu: tính tổng đơn hàng, tạo nội dung CSV cho danh sách khách hàng và tạo lời chào mừng. Vì cả ba đều liên quan đến khách hàng hoặc đơn hàng, chúng được đặt vào một lớp:

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(long unitPriceVnd, int quantity) {}
record Customer(String displayName, String email) {}

final class CustomerUtility {
    long orderSubtotalVnd(List<OrderLine> lines) {
        long total = 0;
        for (OrderLine line : lines) {
            total += line.unitPriceVnd() * line.quantity();
        }
        return total;
    }

    String customerCsv(List<Customer> customers) {
        StringBuilder csv = new StringBuilder("name,email\n");
        for (Customer customer : customers) {
            csv.append(customer.displayName())
               .append(',')
               .append(customer.email())
               .append('\n');
        }
        return csv.toString();
    }

    String welcomeSubject(Customer customer) {
        return "Chào mừng " + customer.displayName();
    }
}
~~~

Đoạn mã ngắn để minh họa trách nhiệm. **Không dùng trực tiếp bản xuất CSV này với dữ liệu không tin cậy**: cần escaping/quoting CSV chính xác và xem xét nguy cơ công thức bảng tính khi mở file. Hàm tính tổng cũng thiếu kiểm tra dữ liệu âm và tràn số; đó là lỗi hợp đồng số học độc lập với vấn đề cohesion.

Đọc từ góc nhìn người bảo trì:

| Phương thức | Mục tiêu | Lý do thay đổi chính |
| --- | --- | --- |
| `orderSubtotalVnd` | Cộng tiền các dòng đơn | Quy định giá, số lượng, đơn vị tiền |
| `customerCsv` | Biểu diễn danh sách khách hàng ở định dạng CSV | Cột báo cáo, encoding/escaping, cách xuất |
| `welcomeSubject` | Tạo tiêu đề chào mừng | Nội dung giao tiếp hoặc bản địa hóa |

Không có **bất biến chung** buộc cả ba phải cùng nằm trong `CustomerUtility`. Người sửa CSV có thể vô tình phải phụ thuộc vào nơi cung cấp giá hoặc template email nếu lớp tiếp tục phình ra.

### 6.1. Chọn ranh giới mới theo trách nhiệm

Một thiết kế rõ hơn có thể phân tách:

~~~text
OrderPricing
  └─ Trách nhiệm: tính tổng đơn hàng hợp lệ

CustomerCsvExporter
  └─ Trách nhiệm: xuất dữ liệu khách hàng thành CSV hợp lệ

WelcomeMessageFactory
  └─ Trách nhiệm: xây dựng nội dung chào mừng
~~~

Điểm mấu chốt là **mỗi đơn vị có một hợp đồng có thể nêu rõ**. Không cần tạo interface riêng cho từng lớp nếu chưa có nhu cầu thay thế cách triển khai, kiểm thử hoặc thay đổi độc lập theo hướng đó. Một utility class stateless và nhỏ vẫn hợp lý khi toàn bộ hàm cùng một nhóm hành vi có ý nghĩa.

### 6.2. Xem chi tiết một đơn vị gắn kết: `OrderPricing`

Giả định nghiệp vụ: giá và tổng tính bằng VND nguyên; đơn giá không âm; số lượng phải dương; khi tổng từ 1.000.000 VND trở lên, khách VIP được giảm 10% tổng trước giảm; phần giảm lấy thương nguyên để phù hợp chính sách minh họa.

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(long unitPriceVnd, int quantity) {}

final class OrderPricing {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    private OrderPricing() {}

    static long subtotalVnd(List<OrderLine> lines) {
        Objects.requireNonNull(lines, "lines");

        long total = 0L;
        for (OrderLine line : lines) {
            Objects.requireNonNull(line, "line");
            if (line.unitPriceVnd() < 0 || line.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }

            long lineAmount = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            total = Math.addExact(total, lineAmount);
        }
        return total;
    }

    static long amountDueVnd(List<OrderLine> lines, boolean vip) {
        long subtotal = subtotalVnd(lines);

        if (vip && subtotal >= VIP_THRESHOLD_VND) {
            long discount = subtotal / 10;
            return subtotal - discount;
        }
        return subtotal;
    }
}
~~~

Các hành vi nội bộ này **có liên hệ chức năng**:

- Kiểm tra đơn giá và số lượng để bảo đảm phép tính có miền giá trị hợp lệ.
- Tính số tiền mỗi dòng rồi cộng tổng bằng phép toán phát hiện tràn.
- Dùng tổng vừa tính làm đầu vào để quyết định và áp dụng ưu đãi VIP.
- Giữ quy tắc ngưỡng và cách tính giảm ở cùng nơi chịu trách nhiệm về giá.

Trong ví dụ này, `OrderPricing` là lớp chỉ chứa các hàm tĩnh và không giữ trạng thái; vẫn có cohesion vì các hàm cùng phục vụ **chính sách tính giá đơn hàng**. Có thể thay bằng đối tượng chính sách với các phụ thuộc được tiêm vào nếu xuất hiện yêu cầu thực tế, nhưng không cần làm vậy trước.

**Lưu ý về hợp đồng:** một danh sách rỗng hiện trả 0 VND. Nếu nghiệp vụ không cho phép đơn rỗng, cần bổ sung ràng buộc. Quy tắc làm tròn, khuyến mãi khác, thuế/phí và đơn vị tiền không được tự suy từ đoạn mã này; chúng cần được xác định trong hệ thống thực.

### 6.3. Vẫn có nơi cần điều phối nhiều đơn vị

Việc tách tính giá không có nghĩa mọi use case phải làm một việc cực nhỏ. Lớp xử lý đặt hàng có thể điều phối:

~~~java
// Mã giả ở cấp use case, các kiểu bên ngoài chỉ thể hiện vai trò.
Receipt checkout(CheckoutCommand command) {
    long amount = OrderPricing.amountDueVnd(
            command.lines(), command.vip());

    PaymentResult paid = paymentPort.charge(
            command.paymentToken(), amount);

    orderStore.save(command.toOrder(amount, paid.reference()));
    return new Receipt(paid.reference(), amount);
}
~~~

`CheckoutCommand`, `PaymentResult`, `paymentPort` và `orderStore` chưa được định nghĩa trong khối mã giả; đây không phải ví dụ độc lập để biên dịch. Mục đích là cho thấy **người đọc nhìn ngay được các bước của một use case**. Kiểm soát transaction, timeout, retry, idempotency và trạng thái thanh toán còn phải được thiết kế và kiểm tra riêng; tách lớp không tự giải quyết chúng.

`CheckoutUseCase` có thể cohesive ở cấp “hoàn tất đặt hàng” dù gọi những thành phần có vai trò khác nhau. Nếu nó tự chứa hàng trăm dòng để tính từng loại thuế, thực hiện protocol HTTP, format email và dựng SQL, cần cân nhắc tách **chi tiết triển khai** ra khỏi điều phối.

## 7. Độ gắn kết với dữ liệu, trạng thái và bất biến

Các phương thức trong một lớp có thể liên quan vì chúng cùng **bảo vệ một bất biến**.

Giả định tài khoản không được âm:

~~~java
final class Account {
    private long balanceVnd;

    Account(long openingBalanceVnd) {
        if (openingBalanceVnd < 0) {
            throw new IllegalArgumentException("Negative balance");
        }
        this.balanceVnd = openingBalanceVnd;
    }

    long balanceVnd() {
        return balanceVnd;
    }

    void deposit(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("Invalid deposit");
        }
        balanceVnd = Math.addExact(balanceVnd, amountVnd);
    }

    void withdraw(long amountVnd) {
        if (amountVnd <= 0 || amountVnd > balanceVnd) {
            throw new IllegalArgumentException("Invalid withdrawal");
        }
        balanceVnd -= amountVnd;
    }
}
~~~

`deposit` và `withdraw` làm hai việc khác nhau về mặt thao tác, nhưng cả hai cùng liên quan trực tiếp đến **quản lý số dư hợp lệ**. Tách chúng thành hai lớp chỉ vì là hai động từ khác nhau có thể khiến bất biến phải sao chép và khó bảo vệ.

Đoạn mã này dùng để minh họa phạm vi trách nhiệm. Trong hệ thống tài chính thật, cần giải quyết đồng thời, lưu trữ bền vững, giao dịch, kiểm toán và quyền truy cập; một đối tượng `Account` trong bộ nhớ chưa đủ bảo đảm tính đúng đắn giữa nhiều yêu cầu song song.

**Câu hỏi trọng tâm:** “Những thành phần này có cùng giữ cho một đối tượng hoặc quy trình ở trạng thái hợp lệ không?” Nếu có, giữ chúng gần nhau đôi khi là quyết định tốt hơn tách quá nhỏ.

## 8. Độ gắn kết cao không đồng nghĩa chia mã càng nhỏ càng tốt

Một số cách “tăng cohesion” bề ngoài có thể làm chất lượng giảm:

- **Tách một công thức thành nhiều hàm không mang ý nghĩa:** người đọc phải nhảy qua sáu phương thức chỉ để thấy một phép nhân.
- **Tạo một interface cho mỗi thao tác:** thêm nhiều tầng điều hướng mà chưa có nhu cầu thay thế, mở rộng hay kiểm thử rõ ràng.
- **Tách các phương thức bảo vệ cùng bất biến sang nhiều lớp:** logic kiểm tra có thể bị phân tán, nhiều nơi có khả năng làm sai trạng thái.
- **Chuyển trạng thái tạm thành đối tượng dùng chung:** để các bước giao tiếp, lớp mới phải chia sẻ dữ liệu nội bộ không cần thiết, tăng coupling và rủi ro đồng thời.
- **Gom mọi thứ theo động từ kỹ thuật:** tất cả hàm `validate` vào một lớp, tất cả hàm `save` vào lớp khác dù liên quan tới các domain khác nhau.

Ngược lại, **không nên cố giữ mọi thứ trong một lớp** chỉ vì tất cả thuộc cùng tính năng. Nếu chính sách tính giá thay đổi độc lập với cách xuất CSV, chúng có lý do rõ ràng để tách.

Một ranh giới hợp lý phải đồng thời giúp:

1. **Nêu mục đích đơn giản:** người mới đọc tên và hợp đồng có thể hiểu chức năng.
2. **Giữ quy tắc liên quan gần nhau:** một thay đổi có phạm vi rõ, không lặp chính sách ở nhiều nơi.
3. **Giữ phụ thuộc có chủ đích:** tách ra không tạo quá nhiều lệnh gọi vòng vo hay chia sẻ trạng thái tùy tiện.
4. **Kiểm thử ở đúng cấp:** kiểm tra quy tắc độc lập và có kiểm thử tích hợp cho toàn quy trình.
5. **Tôn trọng chi phí thay đổi thực tế:** đầu tư cấu trúc phù hợp với độ phức tạp và tần suất thay đổi của thành phần.

## 9. Có thể đo độ gắn kết bằng chỉ số tự động không?

Có các chỉ số nghiên cứu và công cụ như **LCOM (Lack of Cohesion of Methods)**, tập trung xem các phương thức trong lớp chia sẻ trường dữ liệu đến mức nào. Một số biến thể LCOM hoặc heuristic tương tự giúp phát hiện **lớp có nhóm phương thức ít liên hệ về trạng thái**.

Nhưng cần đọc đúng giới hạn:

- Có **nhiều biến thể công thức LCOM** với thang đo khác nhau; không lấy ngưỡng của công cụ này áp cho công cụ khác mà không biết định nghĩa.
- Lớp điều phối hoặc chính sách **không có trạng thái** có thể gắn kết theo chức năng dù các hàm không dùng chung trường.
- Việc hai phương thức dùng cùng một field không chứng minh chúng phục vụ một trách nhiệm: một trường `config` chung có thể được dùng bởi nhiều việc hoàn toàn khác.
- Framework, generated code, data-transfer object, adapter và kiểu tiện ích có mục đích chuyên biệt có thể không phù hợp với tiêu chí dành cho domain class.

Vì vậy chỉ số tự động nên dùng để **gợi ý nơi cần review**, không kết luận một lớp “xấu” hoặc bắt mọi lớp đạt cùng ngưỡng. Muốn quyết định, vẫn phải hiểu trách nhiệm và lý do thay đổi.

### Những tín hiệu quan sát hữu ích khi review

| Tín hiệu | Câu hỏi kế tiếp |
| --- | --- |
| Tên lớp quá rộng | Có thể diễn đạt một mục đích cụ thể hơn không? |
| Ba nhóm phương thức ít liên hệ | Các nhóm có lý do thay đổi độc lập không? |
| Constructor có nhiều phụ thuộc không cùng chức năng | Một nhóm hành vi có cần tất cả phụ thuộc này không? |
| Test một phương thức cần nhiều mock không liên quan | Có thể tách quy tắc thuần khỏi side effect không? |
| Pull request về email phải sửa lớp tính thuế | Hai trách nhiệm đang bị ghép vì lý do gì? |
| Thay đổi một bất biến phải sửa nhiều đơn vị | Có ranh giới đang chia nhỏ quá mức không? |
| Phải truyền object lớn qua mọi hàm | Mỗi hàm thật sự dùng bao nhiêu trường và vì sao? |

Không nên dùng số lượng method, tần suất commit hay số lớp đơn độc để chấm điểm cá nhân hoặc chất lượng kiến trúc.

## 10. Kiểm thử sau khi điều chỉnh ranh giới

Trước khi tách một lớp pha trộn, cần **ghi nhận hành vi đang có** và phân biệt thay đổi cấu trúc với sửa lỗi nghiệp vụ. Ví dụ `CustomerUtility.orderSubtotalVnd` không kiểm tra tràn; `OrderPricing.subtotalVnd` dùng `Math.*Exact` nên sẽ **thay đổi hành vi** ở đầu vào gây tràn. Nếu dự án có dữ liệu như vậy, phải xác định cách xử lý đúng và đưa ra như một thay đổi có chủ đích, không che trong refactor.

Bài kiểm thử JUnit 5 cho quy tắc tính giá đã nêu:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class OrderPricingTest {
    @Test
    void sumsLinesWithoutVipDiscount() {
        long amount = OrderPricing.amountDueVnd(
                List.of(
                        new OrderLine(100_000L, 2),
                        new OrderLine(50_000L, 1)),
                false);

        assertEquals(250_000L, amount);
    }

    @Test
    void appliesVipDiscountAtThreshold() {
        long amount = OrderPricing.amountDueVnd(
                List.of(new OrderLine(1_000_000L, 1)), true);

        assertEquals(900_000L, amount);
    }

    @Test
    void rejectsNegativePriceAndInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPricing.subtotalVnd(
                        List.of(new OrderLine(-1L, 1))));
        assertThrows(IllegalArgumentException.class,
                () -> OrderPricing.subtotalVnd(
                        List.of(new OrderLine(10L, 0))));
    }

    @Test
    void rejectsOverflowInsteadOfSilentlyWrapping() {
        assertThrows(ArithmeticException.class,
                () -> OrderPricing.subtotalVnd(
                        List.of(new OrderLine(Long.MAX_VALUE, 2))));
    }
}
~~~

Các test cho thấy **một nhóm quy tắc gắn kết** có thể được kiểm tra độc lập bằng dữ liệu đơn giản. Tuy nhiên, riêng bài test tính giá không bảo đảm use case thanh toán hoạt động đúng: vẫn cần kiểm tra cách gọi gateway, lưu đơn, xử lý lỗi và dữ liệu trả về ở cấp tích hợp.

Khi tách code trong sản phẩm thật:

1. Viết test mô tả **hành vi hiện tại có chủ đích**; ghi lại các bất thường chưa xác minh.
2. Xác định ranh giới mới theo nhiệm vụ và lý do thay đổi.
3. Chuyển từng phần với sự thay đổi tối thiểu; giữ tên/hợp đồng API khi cần tương thích.
4. Kiểm tra kết quả và tác dụng phụ trước/sau trên các trường hợp đại diện và biên.
5. Xem lại coupling mới: các lớp có phải truy cập lẫn nhau vòng vo hay chia sẻ trạng thái quá nhiều không?
6. Chỉ sửa quy tắc nghiệp vụ khi đặc tả và kiểm thử kỳ vọng đã được xác nhận.

## 11. Cách trao đổi về cohesion trong code review

Phản hồi hiệu quả nên gắn với **thay đổi hoặc khó khăn cụ thể**, không chỉ nói “lớp này thiếu cohesion”.

Ví dụ một nhận xét mang tính xây dựng:

> “Trong `CustomerUtility`, phương thức xuất CSV và phương thức tính tổng đơn hàng thay đổi theo hai bộ yêu cầu độc lập. Khi thay schema báo cáo, ta đang phải sửa và test lớp chứa cả quy tắc tính tiền. Có thể chuyển nhóm xử lý CSV sang `CustomerCsvExporter` và giữ quy tắc giá trong `OrderPricing`, đồng thời thêm test cho phần tính giá và escaping CSV không?”

Nhận xét này có ba phần: **bằng chứng quan sát được**, **chi phí thực tế** và **hướng cải thiện có thể kiểm tra**. Ngược lại, “lớp có 200 dòng nên cần tách làm 5” không đủ chứng minh những ranh giới mới là phù hợp.

### Checklist đánh giá trước khi tách

- [ ] Tôi có thể nói trách nhiệm chính của đơn vị trong một câu cụ thể.
- [ ] Mỗi nhóm mã đều đóng góp cho trách nhiệm đó hoặc bảo vệ cùng bất biến.
- [ ] Tôi đã nhận diện những lý do thay đổi độc lập trong các nhóm mã.
- [ ] Tôi biết dữ liệu nào là trạng thái nội bộ, dữ liệu nào chỉ cần truyền qua tham số.
- [ ] Tôi phân biệt điều phối một use case với tự triển khai chi tiết nhiều trách nhiệm.
- [ ] Tôi đã cân nhắc độ gắn kết **và** mức phụ thuộc sau khi chia tách.
- [ ] Tôi có cách kiểm tra tính đúng đắn và tác dụng phụ khi di chuyển logic.
- [ ] Tôi không thêm interface hoặc lớp trung gian chỉ để đạt một số lượng dòng mong muốn.

## 12. Những ngộ nhận thường gặp

**“Một lớp có nhiều phương thức nghĩa là cohesion thấp.”** Nhiều phương thức có thể cùng bảo vệ một bất biến hoặc triển khai một trách nhiệm rõ.

**“Một lớp chỉ có một phương thức thì chắc chắn gắn kết cao.”** Phương thức đó vẫn có thể làm nhiều công việc độc lập và che dấu các tác dụng phụ không liên quan.

**“Cùng dùng một biến nghĩa là cùng trách nhiệm.”** Chia sẻ field là một dấu hiệu cấu trúc; ý nghĩa nghiệp vụ và lý do thay đổi mới quyết định trách nhiệm.

**“Cùng chạy lúc khởi động thì phải ở cùng một lớp.”** Bootstrapper có thể điều phối gắn kết, nhưng chi tiết cấu hình từng phụ thuộc vẫn cần chủ sở hữu phù hợp.

**“Tách càng nhiều lớp thì cohesion càng cao.”** Quá chia nhỏ có thể làm người đọc mất dấu hành vi và tạo coupling mới.

**“Cohesion và coupling là hai cách gọi của một thứ.”** Cohesion là quan hệ **bên trong**; coupling là phụ thuộc **giữa** đơn vị.

**“Chỉ số LCOM đủ để kết luận thiết kế tốt hay xấu.”** Công thức và ngữ cảnh lớp khác nhau; cần kết hợp đọc code, nghiệp vụ và lịch sử thay đổi.

**“Muốn refactor cấu trúc thì tiện thể sửa luôn mọi lỗi.”** Sửa hành vi nên có đặc tả và kiểm thử riêng để reviewer phân biệt rủi ro và nguyên nhân.

## 13. Câu hỏi tự kiểm tra

1. Vì sao lớp chứa tính giá, xuất CSV và gửi email có thể có độ gắn kết thấp dù ba hành vi đều liên quan đến khách hàng?
2. So sánh độ gắn kết ở cấp một **hàm tính giá**, một **lớp quản lý số dư** và một **module đặt hàng**.
3. Nêu ví dụ về một đơn vị có cohesion cao nhưng coupling vẫn cao. Điều gì cần thay đổi?
4. Một phương thức điều phối xác thực, tính giá, thanh toán và lưu đơn có chắc chắn thiếu gắn kết không? Tại sao?
5. Việc hai phương thức cùng đọc `config` có đủ chứng minh chúng thuộc cùng trách nhiệm không?
6. Nếu tách `CustomerUtility` thành ba đơn vị, những thay đổi nghiệp vụ nào sẽ được khoanh vùng tốt hơn? Tách có thể gây chi phí mới nào?
7. Vì sao `Math.multiplyExact` có thể là thay đổi hành vi so với phép nhân thường khi refactor?
8. LCOM có thể hỗ trợ review kiểu nào? Trường hợp nào khiến nó khó diễn giải?
9. Hãy chọn một lớp bạn từng đọc, viết một câu mô tả trách nhiệm và chỉ ra hai dấu hiệu củng cố hoặc phủ nhận độ gắn kết.
10. Hãy đề xuất một thay đổi nhỏ giúp tăng độ gắn kết nhưng vẫn có kế hoạch kiểm chứng tính đúng đắn và các tác dụng phụ.

## Ghi nhớ

**Độ gắn kết tốt nghĩa là các thành phần trong một đơn vị mã có lý do rõ ràng để cùng tồn tại và cùng chịu trách nhiệm.** Hãy đánh giá dựa trên mục tiêu, bất biến, luồng dữ liệu và những lý do thay đổi có thể quan sát, ở đúng cấp phương thức/lớp/module. Giữ các quy tắc liên quan gần nhau, tách những trách nhiệm thay đổi độc lập khi có lợi ích thực tế, đồng thời kiểm tra coupling và tính đúng đắn sau khi điều chỉnh cấu trúc.
