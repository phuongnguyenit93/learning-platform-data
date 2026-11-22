# Giá trị của việc tách biểu thức khỏi mã Java cố định

Trong một ứng dụng Spring, mã Java thường phải quyết định một đối tượng có đủ điều kiện hay không, chọn dữ liệu nào, tính một giá trị ra sao hoặc tạo khóa cho cache như thế nào. Nếu mọi điều kiện đều được viết trực tiếp bằng các nhánh if/else và phép so sánh trong Java, quy tắc nghiệp vụ sẽ bị gắn chặt vào luồng xử lý. Khi quy tắc thay đổi, lập trình viên phải sửa mã, biên dịch, kiểm thử và triển khai lại ứng dụng.

Spring Expression Language (SpEL) cung cấp một cách biểu diễn những quy tắc dạng biểu thức thành chuỗi có thể phân tích và đánh giá khi chạy. Tách biểu thức khỏi mã Java giúp phần Java tập trung vào việc điều phối và thực thi, còn điều kiện hoặc công thức có thể được mô tả riêng, kiểm thử riêng và thay đổi theo cơ chế cấu hình phù hợp.

## 1. Khi quy tắc bị cố định trong mã Java

Giả sử hệ thống chỉ cho phép duyệt một đơn hàng khi tổng tiền đạt một ngưỡng và khách hàng thuộc hạng GOLD:

    public boolean canApprove(Order order) {
        return order.getTotalVnd() >= 1_000_000
                && "GOLD".equals(order.getCustomerTier());
    }

Đoạn mã này dễ đọc và hoàn toàn hợp lý khi quy tắc ổn định. Tuy nhiên, nếu bộ phận nghiệp vụ đổi ngưỡng thành 1.500.000 hoặc thêm hạng PLATINUM, điều kiện phải được sửa trong mã nguồn. Nếu cùng một quy tắc xuất hiện ở nhiều service, các nơi đó có thể bị cập nhật không đồng bộ. Một thay đổi nhỏ về chính sách khi ấy kéo theo việc sửa mã, chạy lại kiểm thử và phát hành phiên bản mới.

Vấn đề không nằm ở việc dùng if là sai. Java vẫn là nơi phù hợp để triển khai thuật toán, xử lý trạng thái, giao dịch và các hành động có tác động. Vấn đề xuất hiện khi một điều kiện có thể cấu hình hoặc thường xuyên thay đổi bị trộn vào phần điều phối vốn ít thay đổi hơn.

## 2. Biểu thức được tách ra hoạt động như thế nào?

SpEL cho phép viết điều kiện trên thành một chuỗi:

    totalVnd >= 1000000 and customerTier == 'GOLD'

Chuỗi này không tự chạy như mã Java. Spring dùng ExpressionParser để phân tích nó thành một đối tượng Expression. Khi cần kết quả, ứng dụng cung cấp EvaluationContext chứa đối tượng dữ liệu hoặc các biến mà biểu thức được phép truy cập, sau đó yêu cầu Expression đánh giá biểu thức trong ngữ cảnh đó.

Có thể hình dung quy trình gồm bốn phần:

1. **Biểu thức:** mô tả điều kiện hoặc phép tính, ví dụ totalVnd >= 1000000.
2. **Parser:** phân tích chuỗi và tạo đối tượng Expression.
3. **EvaluationContext:** cung cấp dữ liệu đầu vào, biến và những khả năng truy cập được cho phép.
4. **Evaluation:** tính kết quả theo dữ liệu hiện tại, chẳng hạn true hoặc false.

Điểm quan trọng là biểu thức chỉ quyết định dựa trên dữ liệu mà ứng dụng đưa vào context. SpEL không tự truy vấn cơ sở dữ liệu, không tự mở giao dịch và không thay thế trách nhiệm của service.

## 3. Ví dụ: đưa điều kiện duyệt đơn hàng vào cấu hình

Ta có thể đặt biểu thức trong cấu hình ứng dụng:

    approval:
      rule: "totalVnd >= 1000000 and customerTier == 'GOLD'"

Đối tượng dữ liệu đầu vào chỉ công bố những thuộc tính mà quy tắc cần dùng:

    public class OrderFacts {
        private final long totalVnd;
        private final String customerTier;

        public OrderFacts(long totalVnd, String customerTier) {
            this.totalVnd = totalVnd;
            this.customerTier = customerTier;
        }

        public long getTotalVnd() {
            return totalVnd;
        }

        public String getCustomerTier() {
            return customerTier;
        }
    }

Một component có thể nạp chuỗi cấu hình, phân tích biểu thức một lần và đánh giá nó cho từng đơn hàng:

    @Component
    public class ApprovalRule {
        private final Expression expression;

        public ApprovalRule(@Value("${approval.rule}") String source) {
            ExpressionParser parser = new SpelExpressionParser();
            this.expression = parser.parseExpression(source);
        }

        public boolean matches(OrderFacts facts) {
            EvaluationContext context =
                    SimpleEvaluationContext.forReadOnlyDataBinding()
                            .withRootObject(facts)
                            .build();

            Boolean result = expression.getValue(context, Boolean.class);
            return Boolean.TRUE.equals(result);
        }
    }

Ở đây, @Value lấy chuỗi từ cấu hình Spring. Chuỗi đó được chuyển cho SpEL parser để phân tích; nó không cần bọc thêm #{...} vì ứng dụng đang chủ động gọi parser. SimpleEvaluationContext được chọn vì ví dụ chỉ cần đọc thuộc tính và so sánh. Nó giới hạn các khả năng của biểu thức so với StandardEvaluationContext, phù hợp hơn khi quy tắc chỉ cần truy cập dữ liệu đầu vào.

Service vẫn chịu trách nhiệm lấy đơn hàng, tạo OrderFacts và quyết định hành động tiếp theo:

    OrderFacts facts = new OrderFacts(
            order.getTotalVnd(),
            order.getCustomerTier());

    if (approvalRule.matches(facts)) {
        approvalService.approve(order);
    }

Phần Java vẫn giữ luồng nghiệp vụ và hành động duyệt đơn. Điều kiện được đưa ra cấu hình, nên khi ngưỡng hoặc hạng khách hàng thay đổi, nhóm vận hành có thể cập nhật cấu hình theo quy trình triển khai cấu hình của hệ thống. Nếu cấu hình chỉ được nạp lúc khởi động, ứng dụng vẫn cần khởi động lại hoặc có cơ chế reload; tách biểu thức không tự động làm cho mọi thay đổi có hiệu lực tức thì.

## 4. Giá trị thực tế của việc tách biểu thức

### Tách chính sách khỏi luồng thực thi

Service có thể giữ nhiệm vụ điều phối: nạp dữ liệu, kiểm tra quyền truy cập, gọi quy tắc và thực hiện hành động. Biểu thức mô tả tiêu chí quyết định. Khi chính sách thay đổi, phạm vi cần xem xét thường nhỏ hơn và ít làm xáo trộn phần xử lý còn lại.

Ranh giới này đặc biệt hữu ích với các ngưỡng, điều kiện đủ tư cách, bộ lọc, công thức tính điểm hoặc lựa chọn theo thuộc tính. Java vẫn sở hữu quy trình và tính đúng đắn của nghiệp vụ; biểu thức chỉ mô tả phần điều kiện đã được xác định rõ.

### Giảm việc sửa mã cho thay đổi mang tính cấu hình

Khi biểu thức được lấy từ cấu hình ngoài mã nguồn, một số thay đổi có thể được thực hiện bằng cách cập nhật cấu hình thay vì sửa Java. Điều này hữu ích với những quy tắc thay đổi theo môi trường, khách hàng hoặc chính sách vận hành.

Lợi ích này phụ thuộc vào cách quản lý cấu hình. Cấu hình đóng gói trong file và chỉ nạp lúc khởi động vẫn cần một lần khởi động lại để nhận giá trị mới. Muốn thay đổi động, hệ thống phải có nguồn cấu hình động, cơ chế làm mới và cách xử lý phiên bản quy tắc rõ ràng.

### Dùng chung một cơ chế đánh giá

Thay vì tự viết nhiều bộ xử lý điều kiện dạng chuỗi, ứng dụng có thể dùng parser và context thống nhất. Mỗi quy tắc nhận một tập dữ liệu đầu vào xác định và trả về một kiểu kết quả đã định trước. Điều này làm cho cách lưu trữ, nạp, kiểm tra cú pháp và đánh giá quy tắc nhất quán hơn.

### Biểu đạt ý định ngắn gọn

Các biểu thức như:

    quantity > 0 and unitPrice * quantity <= creditLimit

hoặc:

    customer.active and customer.region == 'VN'

thể hiện trực tiếp điều kiện cần kiểm tra. Với quy tắc ngắn, cách viết này thường dễ đối chiếu với chính sách nghiệp vụ hơn một đoạn mã điều khiển dài.

### Hỗ trợ các điểm mở rộng có sẵn trong Spring

SpEL đã được tích hợp vào nhiều tính năng của Spring. Ví dụ, @Value có thể dùng biểu thức để lấy giá trị từ môi trường Spring:

    @Value("#{systemProperties['user.timezone']}")
    private String timeZone;

Spring Cache dùng SpEL để tạo khóa từ tham số của phương thức:

    @Cacheable(cacheNames = "orders", key = "#order.id")
    public Order findOrder(Order order) {
        // ...
    }

Spring Method Security cũng dùng biểu thức để mô tả điều kiện cấp quyền:

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Order order) {
        // ...
    }

Trong các ví dụ này, Spring cung cấp context riêng cho từng tính năng. Những tên như #order, authentication hoặc các hàm như hasAuthority chỉ có ý nghĩa khi context tương ứng đã cung cấp chúng. Không nên mặc định rằng mọi biểu thức SpEL đều có cùng biến hoặc cùng quyền truy cập.

## 5. Tách biểu thức không có nghĩa là đưa toàn bộ nghiệp vụ ra khỏi Java

SpEL phù hợp với biểu thức có đầu vào và kết quả rõ ràng: điều kiện đúng/sai, phép tính, truy cập thuộc tính, lựa chọn phần tử hoặc tạo khóa. Nó không phải nơi lý tưởng để triển khai một quy trình nghiệp vụ dài có nhiều bước, cập nhật nhiều aggregate, gọi dịch vụ bên ngoài hoặc xử lý giao dịch.

Một ranh giới thực tế là:

- **Java/service/domain:** xác định dữ liệu đầu vào, kiểm soát quyền, giao dịch, thứ tự các bước, thay đổi trạng thái, gọi hệ thống khác và xử lý lỗi.
- **SpEL:** đánh giá một điều kiện hoặc công thức nhỏ trên dữ liệu mà Java đã chuẩn bị.
- **Cấu hình hoặc kho quy tắc:** lưu biểu thức nếu quy tắc cần được quản lý độc lập với mã nguồn.

Nếu biểu thức trở thành một đoạn logic nhiều dòng, khó đọc hoặc cần nhiều hành động phụ thuộc nhau, hãy chuyển phần đó thành phương thức Java có tên rõ nghĩa. Có thể giữ một biểu thức ngắn để quyết định có gọi phương thức hay không, nhưng không nên biến chuỗi SpEL thành một ngôn ngữ lập trình thứ hai của ứng dụng.

## 6. Context là ranh giới dữ liệu và quyền truy cập

EvaluationContext quyết định biểu thức nhìn thấy dữ liệu nào và được phép thực hiện thao tác gì. Đối tượng gốc (root object) thường là dữ liệu nghiệp vụ đã được chuẩn bị; context cũng có thể chứa biến hoặc tham chiếu bean nếu ứng dụng chủ động đăng ký.

Nên tạo một đối tượng đầu vào nhỏ, chỉ có những thuộc tính cần thiết. Cách này giúp quy tắc dễ hiểu, dễ kiểm thử và ít phụ thuộc vào cấu trúc nội bộ của entity hoặc service. Tránh đưa cả một object graph lớn hoặc những bean có nhiều quyền vào context khi biểu thức không cần đến chúng.

SimpleEvaluationContext hỗ trợ một tập tính năng giới hạn và cho phép chọn property accessor phù hợp. StandardEvaluationContext có khả năng rộng hơn, bao gồm truy cập phương thức, kiểu và bean tùy cấu hình. Chỉ nên bật các khả năng thực sự cần thiết. Đặc biệt, không được lấy biểu thức tùy ý từ người dùng bên ngoài rồi đánh giá bằng context có quyền truy cập rộng: biểu thức có thể gọi phương thức hoặc truy cập tài nguyên vượt quá ý định ban đầu.

## 7. Phân tích cú pháp, kiểu kết quả và lỗi khi chạy

Cần phân biệt hai thời điểm:

- **Parse:** kiểm tra cú pháp chuỗi và tạo Expression. Biểu thức sai cú pháp thường có thể được phát hiện khi component nạp cấu hình.
- **Evaluate:** chạy biểu thức với dữ liệu thực tế. Lỗi có thể xuất hiện nếu thuộc tính không tồn tại, dữ liệu null, phép chuyển kiểu không hợp lệ hoặc kết quả không đúng kiểu mong đợi.

Khi dùng quy tắc cho một quyết định quan trọng, nên khai báo rõ kiểu kết quả mong đợi, ví dụ Boolean.class cho điều kiện. Cần xác định cách xử lý kết quả null và lỗi đánh giá: từ chối thao tác, dùng giá trị mặc định đã được nghiệp vụ chấp thuận, hay dừng xử lý và báo lỗi. Không nên âm thầm coi lỗi biểu thức là true.

Một số thực hành hữu ích:

- Phân tích biểu thức một lần khi nạp cấu hình, sau đó tái sử dụng đối tượng Expression; tránh parse lại cùng một chuỗi trong mỗi request.
- Tạo EvaluationContext cho dữ liệu của lần đánh giá hiện tại; không dùng chung context chứa root object của nhiều request.
- Kiểm thử biểu thức với trường hợp đúng, sai, biên ngưỡng, giá trị null và dữ liệu không hợp lệ.
- Kiểm tra biểu thức ngay khi ứng dụng khởi động để cấu hình sai được phát hiện sớm.
- Ghi nhận mã hoặc phiên bản quy tắc cùng lỗi đánh giá để có thể truy vết, nhưng tránh ghi dữ liệu nhạy cảm của đối tượng đầu vào vào log.

## 8. Khi nào nên dùng SpEL?

SpEL là lựa chọn phù hợp khi biểu thức ngắn, có dữ liệu đầu vào rõ ràng, có kiểu kết quả xác định và có lý do thực tế để quản lý nó độc lập với mã Java. Những trường hợp thường gặp gồm:

- Điều kiện lọc hoặc đủ điều kiện dựa trên một số thuộc tính.
- Ngưỡng, hệ số hoặc công thức đơn giản được quản lý qua cấu hình.
- Khóa cache được suy ra từ tham số phương thức.
- Điều kiện bảo mật tại các điểm mà Spring Security hỗ trợ SpEL.
- Giá trị cấu hình cần truy cập bean, property hoặc system property theo cơ chế Spring cho phép.

Nên giữ logic trong Java khi cần nhiều bước, vòng đời phức tạp, side effect, xử lý giao dịch, kiểm soát lỗi chi tiết hoặc khi biểu thức trở nên khó đọc hơn một phương thức có tên rõ ràng.

## Kết luận

Giá trị cốt lõi của việc tách biểu thức khỏi mã Java cố định là tạo ra một ranh giới rõ ràng giữa **cách ứng dụng thực thi** và **điều kiện mà ứng dụng dùng để ra quyết định**. Java giữ cấu trúc, trạng thái và hành động; SpEL diễn đạt những điều kiện hoặc công thức nhỏ; cấu hình có thể quản lý các biểu thức đó theo vòng đời phù hợp.

Lợi ích chỉ xuất hiện khi ranh giới được thiết kế có chủ đích: dữ liệu đưa vào context phải tối thiểu, quyền của biểu thức phải được giới hạn, kiểu kết quả phải rõ ràng và quy tắc phải được kiểm thử. Khi áp dụng đúng phạm vi, SpEL giúp các thay đổi về chính sách dễ quản lý hơn mà không làm luồng nghiệp vụ Java trở nên khó hiểu.