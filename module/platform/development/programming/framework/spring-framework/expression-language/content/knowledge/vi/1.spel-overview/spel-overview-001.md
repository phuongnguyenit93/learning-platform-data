# Spring Expression Language (SpEL) là gì và giải quyết bài toán nào

Spring Expression Language (SpEL) là ngôn ngữ biểu thức do Spring cung cấp để đọc, tính toán và thao tác với dữ liệu của ứng dụng tại thời điểm chạy. Một biểu thức có thể lấy thuộc tính từ một object, gọi phương thức, so sánh giá trị, tính toán, truy cập phần tử trong collection hoặc kết hợp nhiều điều kiện để trả về một kết quả.

SpEL giúp Spring và ứng dụng mô tả những quy tắc ngắn gọn ngay tại nơi cấu hình hoặc khai báo hành vi cần dùng chúng. Thay vì viết thêm nhiều đoạn Java chỉ để lấy một giá trị hay kiểm tra một điều kiện đơn giản, ta có thể khai báo biểu thức và để Spring đánh giá nó trên dữ liệu thực tế.

## Bài toán SpEL giải quyết

Trong ứng dụng Spring, nhiều quyết định phụ thuộc vào trạng thái của object hoặc cấu hình tại thời điểm chạy:

- Giá trị cấu hình cần được tính từ một thuộc tính khác, một system property hoặc một bean.
- Một hành vi chỉ được thực hiện khi object thỏa mãn điều kiện nhất định.
- Khóa cache cần lấy từ tham số của phương thức.
- Một quy tắc cần đọc dữ liệu lồng nhau trong object hoặc collection.
- Một annotation cần tham chiếu đến tham số, kết quả trả về hoặc thông tin của đối tượng hiện tại.

Nếu xử lý tất cả bằng Java, mỗi nơi có thể cần thêm getter, câu lệnh điều kiện, phép tính hoặc đoạn mã nối dữ liệu. Với những quy tắc ngắn và mang tính khai báo, cách này làm cấu hình dài hơn và khiến ý định của cấu hình khó nhận ra.

SpEL cung cấp một cách biểu diễn thống nhất cho các biểu thức đó. Spring có thể đánh giá biểu thức khi tạo bean hoặc tại điểm tích hợp tương ứng; ứng dụng cũng có thể chủ động phân tích và đánh giá biểu thức bằng API.

## SpEL hoạt động như thế nào?

Có thể hình dung quá trình sử dụng SpEL qua ba thành phần:

1. **Expression parser** nhận chuỗi biểu thức và phân tích cú pháp. API thường dùng là **SpelExpressionParser**.
2. **Expression** là biểu diễn đã được phân tích. Ta có thể lấy giá trị, lấy giá trị theo kiểu mong muốn hoặc gán giá trị nếu biểu thức cho phép.
3. **Evaluation context** cung cấp môi trường để đánh giá biểu thức: object gốc, biến, hàm, cách truy cập thuộc tính, cách phân giải bean và các khả năng được cho phép.

Object gốc được gọi là **root object**. Nếu biểu thức viết **status == 'PAID'**, SpEL tìm thuộc tính **status** trên root object hoặc trong ngữ cảnh được cung cấp. Các biến được tham chiếu bằng dấu **#**, ví dụ **#customerId**. Trong một số tích hợp, Spring tự chuẩn bị root object và các biến phù hợp với ngữ cảnh đó.

Một luồng sử dụng độc lập thường gồm: tạo parser, phân tích biểu thức, tạo evaluation context với dữ liệu cần đánh giá, rồi lấy kết quả. Có thể phân tích biểu thức một lần và tái sử dụng đối tượng Expression cho nhiều lần đánh giá.

## Ví dụ sử dụng độc lập

Giả sử ứng dụng có một đơn hàng với trạng thái và tổng tiền. Ta muốn kiểm tra đơn hàng có đủ điều kiện chuyển sang bước giao hàng hay không.

~~~java
public class Order {
    private final String status;
    private final BigDecimal total;

    public Order(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Có thể dùng SpEL để diễn đạt điều kiện:

~~~java
Order order = new Order("PAID", new BigDecimal("120.00"));

ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext(order);

Expression expression =
        parser.parseExpression("status == 'PAID' and total > 0");

Boolean canShip = expression.getValue(context, Boolean.class);
~~~

Ở đây, **order** là root object. Biểu thức đọc hai thuộc tính, so sánh trạng thái và tổng tiền, sau đó trả về kết quả Boolean. Java vẫn tạo object và quyết định cách xử lý kết quả; SpEL đảm nhiệm phần diễn đạt và đánh giá điều kiện.

Ví dụ này cũng cho thấy SpEL không tự biết dữ liệu của ứng dụng. Muốn biểu thức truy cập được thuộc tính hay biến nào, ứng dụng phải cung cấp object hoặc context phù hợp.

## SpEL khi tích hợp với Spring

Điểm mạnh của SpEL là được dùng trực tiếp trong nhiều cơ chế của Spring. Trong annotation hoặc cấu hình Spring, biểu thức thường được đặt trong dấu **#{...}**.

Ví dụ, lấy một system property để gán cho bean:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timeZone;
~~~

Ví dụ trên yêu cầu Spring đánh giá biểu thức và inject kết quả vào field. SpEL cũng có thể tham chiếu đến thuộc tính của bean khác, thực hiện phép tính hoặc chọn giá trị theo điều kiện.

Một ví dụ khác đến từ Spring Cache:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(String isbn) {
    // Load book
}
~~~

**#isbn** tham chiếu đến tham số của phương thức. Spring dùng giá trị đó làm cache key. Nhờ vậy, quy tắc tạo khóa được khai báo ngay tại annotation mà không cần tự viết một lớp tạo key cho trường hợp đơn giản.

Spring Security cũng sử dụng SpEL trong các biểu thức phân quyền như **@PreAuthorize**. Đây là ví dụ về cách các module trong hệ sinh thái Spring dùng chung một ngôn ngữ biểu thức để mô tả điều kiện theo ngữ cảnh riêng của module.

Lưu ý: dấu **#{...}** là cách nhúng biểu thức trong các điểm tích hợp của Spring. Khi gọi API parser trực tiếp, thông thường ta truyền phần biểu thức bên trong, chẳng hạn **status == 'PAID'**, chứ không cần bọc nó trong **#{...}**.

## Những khả năng chính

Ở mức tổng quan, SpEL hỗ trợ các nhóm thao tác sau:

- **Truy cập dữ liệu:** đọc thuộc tính, gọi phương thức, đi qua các thuộc tính lồng nhau và truy cập phần tử của mảng, list hoặc map.
- **Tính toán và so sánh:** phép toán số học, so sánh, logic, kiểm tra kiểu, biểu thức chính quy và điều kiện ba ngôi.
- **Tham chiếu ngữ cảnh:** dùng root object, biến như **#name**, hoặc tham chiếu bean như **@someBean** khi evaluation context cho phép.
- **Làm việc với collection:** lọc phần tử bằng selection, biến đổi phần tử bằng projection và truy cập phần tử theo chỉ mục.
- **Tương tác với kiểu dữ liệu:** trong context phù hợp, có thể tham chiếu kiểu Java, tạo object hoặc gọi các chức năng được expose cho biểu thức.

Ví dụ, **items.?[active]** chọn các phần tử có thuộc tính **active** đúng; **items.![name]** tạo collection mới chứa giá trị **name** của từng phần tử. Đây là những thao tác hữu ích khi cần mô tả việc lọc hoặc lấy dữ liệu mà không viết vòng lặp trong cấu hình.

Không phải mọi evaluation context đều cho phép tất cả khả năng trên. Khả năng thực tế phụ thuộc vào loại context, property accessor, method resolver, bean resolver và các thành phần mà ứng dụng đăng ký.

## Phân biệt SpEL với property placeholder

Trong cấu hình Spring, hai cú pháp thường gặp có mục đích khác nhau:

- **Property placeholder** **${app.page-size:20}** lấy giá trị cấu hình từ nguồn thuộc tính, có thể dùng giá trị mặc định nếu thuộc tính chưa được khai báo.
- **SpEL** **#{...}** đánh giá một biểu thức. Biểu thức có thể đọc dữ liệu, thực hiện phép tính hoặc kết hợp nhiều giá trị.

Ví dụ:

~~~java
@Value("${app.page-size:20}")
private int pageSize;

@Value("#{T(java.lang.Math).max(10, 2 * 8)}")
private int calculatedLimit;
~~~

Field đầu tiên nhận giá trị cấu hình **app.page-size**, mặc định là **20**. Field thứ hai nhận kết quả của biểu thức SpEL. Property placeholder phù hợp để đưa giá trị cấu hình vào ứng dụng; SpEL phù hợp khi cần tính toán hoặc diễn đạt logic trên những giá trị đó.

## Khi nào nên dùng SpEL?

SpEL phù hợp khi biểu thức ngắn, có ý nghĩa khai báo và nằm tại một điểm tích hợp rõ ràng, chẳng hạn:

- Tính một giá trị cấu hình từ các giá trị đã có.
- Khai báo điều kiện hoặc khóa trong annotation được Spring hỗ trợ.
- Truy cập một thuộc tính hoặc tham số trong ngữ cảnh mà framework cung cấp.
- Lọc hoặc trích xuất dữ liệu từ collection trong một biểu thức đơn giản.
- Cho phép cấu hình một quy tắc nhỏ mà không cần tạo thêm lớp Java chỉ để thực hiện một phép tính hoặc phép so sánh.

Nên chuyển logic sang Java khi quy tắc có nhiều nhánh, nhiều bước xử lý, cần gọi nhiều dịch vụ, cần xử lý lỗi phức tạp hoặc cần được kiểm thử và tái sử dụng như một phần rõ ràng của nghiệp vụ. Một biểu thức dài có thể khó đọc, khó tìm lỗi và che giấu phụ thuộc hơn một phương thức Java có tên rõ ràng.

SpEL là ngôn ngữ biểu thức, không thay thế toàn bộ Java và cũng không tự động biến một ứng dụng thành hệ thống quản lý luật nghiệp vụ. Nó phát huy hiệu quả nhất ở những điểm mà framework đã thiết kế để nhận biểu thức.

## Evaluation context và an toàn

Evaluation context quyết định biểu thức được phép nhìn thấy và thực hiện những gì. **StandardEvaluationContext** cung cấp nhiều khả năng, bao gồm truy cập thuộc tính, gọi phương thức và các cơ chế mở rộng khác. Điều đó thuận tiện cho biểu thức do lập trình viên kiểm soát, nhưng cũng có nghĩa là biểu thức có thể có quyền truy cập đáng kể vào ứng dụng.

Không nên lấy biểu thức tùy ý từ người dùng rồi đánh giá bằng một context có quyền rộng. Nếu cần đánh giá biểu thức do bên ngoài cung cấp, hãy giới hạn root object, biến và thuộc tính được expose; chỉ đăng ký những accessor hoặc resolver cần thiết. Có thể cân nhắc **SimpleEvaluationContext** cho các trường hợp data binding cần tập con khả năng bị giới hạn. Context này không cung cấp toàn bộ khả năng của **StandardEvaluationContext**, chẳng hạn các tham chiếu kiểu, constructor và bean reference; việc truy cập phương thức cũng bị giới hạn theo cấu hình.

Với biểu thức được dùng lặp lại, nên phân tích trước và tái sử dụng **Expression** thay vì tạo parser và parse lại chuỗi trong mỗi lần gọi. Context và root object vẫn cần phù hợp với từng lần đánh giá. Điều này giúp giảm công việc phân tích cú pháp lặp lại và làm rõ ranh giới giữa biểu thức với dữ liệu đầu vào.

## Kết luận

SpEL là lớp ngôn ngữ biểu thức giúp Spring kết nối cấu hình khai báo với dữ liệu và trạng thái thực tế của ứng dụng. Nó giải quyết nhu cầu đọc thuộc tính, tính toán giá trị và mô tả điều kiện tại các điểm tích hợp như **@Value**, Spring Cache và Spring Security. Khi dùng đúng phạm vi, SpEL làm cấu hình ngắn gọn và linh hoạt; khi logic trở nên phức tạp hoặc cần đánh giá đầu vào không đáng tin cậy, cần đưa xử lý về Java hoặc giới hạn evaluation context một cách chặt chẽ.
