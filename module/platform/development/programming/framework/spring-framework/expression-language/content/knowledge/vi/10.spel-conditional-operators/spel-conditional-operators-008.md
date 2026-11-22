# Nguy cơ làm thay đổi trạng thái qua biểu thức

SpEL có thể thực hiện thao tác ghi dữ liệu, không chỉ đọc property hoặc tính ra một giá trị. Toán tử gán **=** cho phép biểu thức cập nhật property hoặc vị trí có thể ghi thông qua EvaluationContext. Vì vậy, khi một biểu thức được đánh giá bằng **getValue(...)**, object gốc vẫn có thể bị thay đổi nếu chuỗi biểu thức chứa phép gán và context cho phép thao tác đó.

Rủi ro xuất hiện khi biểu thức được đặt ở nơi người đọc kỳ vọng chỉ có thao tác đọc, chẳng hạn một điều kiện, một cấu hình hoặc một phép tính. Một phép gán ẩn trong chuỗi SpEL có thể làm thay đổi trạng thái nghiệp vụ, kích hoạt logic trong setter và ảnh hưởng đến những đoạn xử lý chạy sau đó.

## Phép gán có thể nằm ngay trong biểu thức

Ví dụ, giả sử ứng dụng có một đối tượng đơn hàng:

~~~java
public class Order {
    private String status;

    public Order(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Có thể tạo một biểu thức gán trạng thái:

~~~java
Order order = new Order("PENDING");

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("status = 'APPROVED'");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Object result = expression.getValue(context);
~~~

Khi biểu thức được đánh giá, SpEL tìm property status trên root object và thực hiện phép gán nếu property accessor cho phép ghi. Sau khi đánh giá, **order.getStatus()** trả về **APPROVED**. Giá trị trả về của biểu thức không phải bằng chứng rằng thao tác chỉ đọc; chính quá trình evaluate đã làm thay đổi object.

Điều này khác với một biểu thức chỉ đọc như **status == 'APPROVED'**. Biểu thức so sánh trả về Boolean mà không chủ động gán giá trị mới cho status.

## Vì sao getValue có thể tạo side effect?

Tên **getValue(...)** thường được hiểu là lấy giá trị. Tuy nhiên, API này yêu cầu SpEL đánh giá toàn bộ biểu thức. Nếu biểu thức có toán tử gán, lời gọi phương thức, hoặc một thao tác khác có tác động phụ được context hỗ trợ, quá trình đánh giá có thể làm thay đổi trạng thái.

So sánh hai biểu thức:

~~~java
Expression readExpression =
        parser.parseExpression("status == 'PENDING'");

Expression writeExpression =
        parser.parseExpression("status = 'APPROVED'");

Boolean isPending =
        readExpression.getValue(context, Boolean.class);

Object assignmentResult =
        writeExpression.getValue(context);
~~~

Biểu thức đầu kiểm tra trạng thái hiện tại. Biểu thức thứ hai cập nhật trạng thái. Cả hai đều có thể được gọi bằng getValue, nhưng ý nghĩa và tác động hoàn toàn khác nhau.

Do đó, không nên đánh giá mức độ an toàn chỉ dựa vào tên API được gọi. Cần xem nội dung biểu thức, root object và các khả năng mà evaluation context cung cấp.

## Những vùng dữ liệu có thể bị thay đổi

Phép gán có thể tác động đến bất kỳ vị trí nào mà property accessor hoặc cơ chế truy cập tương ứng cho phép ghi. Các trường hợp thường gặp gồm:

- **Property của JavaBean:** gán vào property thông qua setter.
- **Property lồng nhau:** cập nhật một thuộc tính ở sâu trong object graph, ví dụ **customer.address.city**.
- **Phần tử collection hoặc array:** thay thế phần tử tại một chỉ mục có thể ghi, ví dụ **items[0]**.
- **Map entry:** cập nhật giá trị tại một key nếu accessor hỗ trợ thao tác đó.
- **Đối tượng dữ liệu được chia sẻ:** thay đổi root object hoặc object lồng nhau mà các thành phần khác cũng đang tham chiếu.

Ví dụ, **address.city = 'Da Nang'** có thể cập nhật city của object address. Biểu thức **items[0] = 'Updated'** có thể thay phần tử đầu tiên của một collection. Những thao tác này phụ thuộc cấu trúc object, khả năng ghi của accessor và kiểu dữ liệu đích.

Nếu property không có setter, collection không hỗ trợ cập nhật hoặc vị trí đích không tồn tại, thao tác ghi có thể thất bại trong lúc evaluation. Việc biểu thức parse thành công không có nghĩa mọi phép gán sẽ thực hiện được trên mọi object.

## Setter có thể kích hoạt logic nghiệp vụ

Khi property được cập nhật thông qua setter, side effect có thể rộng hơn việc thay giá trị field. Setter có thể xác thực chuyển trạng thái, ghi thời điểm cập nhật, phát sự kiện hoặc thay đổi các thuộc tính liên quan.

~~~java
public void setStatus(String nextStatus) {
    validateTransition(this.status, nextStatus);
    this.status = nextStatus;
    this.updatedAt = Instant.now();
    publishStatusChangedEvent();
}
~~~

Nếu biểu thức SpEL gán vào property status và property accessor gọi setter này, toàn bộ logic trong setter có thể chạy. Một biểu thức ngắn như **status = 'APPROVED'** vì vậy có thể kích hoạt nhiều hành động mà người đọc không nhìn thấy trực tiếp trong chuỗi biểu thức.

Đây là lý do không nên dùng phép gán SpEL để thay thế một lệnh nghiệp vụ quan trọng. Nếu chuyển trạng thái cần kiểm tra quyền, xác thực quy tắc, ghi audit hoặc phối hợp nhiều đối tượng, hãy gọi một service method có tên thể hiện rõ hành động đó.

## Đánh giá lặp lại có thể lặp lại side effect

Một Expression có thể được parse một lần và tái sử dụng. Việc tái sử dụng đối tượng Expression không làm cho biểu thức trở thành chỉ đọc. Mỗi lần evaluate, phép gán trong biểu thức có thể lại được thực hiện.

Ngay cả khi biểu thức gán cùng một giá trị, setter vẫn có thể chạy nhiều lần. Điều này có thể tạo ra nhiều event, cập nhật timestamp lặp lại, ghi audit trùng hoặc gọi logic phụ nhiều lần.

Tình huống dễ gặp là một biểu thức được khai báo trong cấu hình và được framework đánh giá mỗi khi có yêu cầu. Nếu biểu thức chứa phép gán, hành vi của hệ thống có thể phụ thuộc số lần framework đánh giá và thứ tự thực hiện. Điều này làm kết quả khó dự đoán hơn so với một biểu thức thuần đọc dữ liệu.

Với biểu thức được dùng trong điều kiện, cache key hoặc cấu hình có thể được đánh giá nhiều lần, hãy giữ biểu thức không có side effect. Nếu cần cập nhật, thực hiện thao tác ghi tại một điểm trong luồng nghiệp vụ mà ứng dụng kiểm soát rõ ràng.

## Tác động đến object được chia sẻ giữa nhiều thành phần

Root object có thể được nhiều service, component hoặc request cùng tham chiếu. Khi một biểu thức thay đổi object đó, mọi thành phần đang giữ tham chiếu có thể quan sát trạng thái mới.

Ví dụ, một object cấu hình được chia sẻ có thể đang được nhiều request sử dụng. Một phép gán vào property trong lúc một request khác đang đọc property có thể khiến kết quả phụ thuộc thời điểm thực thi. Nếu nhiều luồng cùng ghi, ứng dụng còn phải xử lý tính nhất quán và đồng bộ.

SpEL không tự tạo khóa, transaction hay cơ chế đồng bộ cho object được thay đổi. Các bảo đảm đó thuộc về thiết kế ứng dụng. Không nên đưa object dùng chung hoặc object có vòng đời dài vào một evaluation context có quyền ghi nếu không có quy tắc kiểm soát rõ ràng.

## Thay đổi trong bộ nhớ và dữ liệu lưu trữ

Một phép gán SpEL trực tiếp thay đổi object trong bộ nhớ. Nó không tự gọi repository, mở transaction hoặc ghi dữ liệu xuống database.

Tuy nhiên, nếu root object là entity đang được persistence context quản lý, thay đổi property có thể được ORM phát hiện. Khi transaction được flush hoặc commit, thay đổi đó có thể được ghi xuống database theo cơ chế dirty checking của persistence provider.

Điều này có nghĩa là side effect có thể vượt ra ngoài phạm vi của biểu thức. Một dòng cấu hình chứa phép gán có thể gián tiếp làm thay đổi dữ liệu bền vững nếu object được quản lý trong transaction hiện tại.

Với entity nghiệp vụ, nên thực hiện cập nhật trong service method có transaction boundary và kiểm tra hợp lệ. SpEL có thể dùng để mô tả điều kiện hoặc truy xuất giá trị, còn việc thay đổi trạng thái nên nằm ở nơi có thể quan sát và kiểm soát.

## Hạn chế khả năng ghi bằng EvaluationContext

EvaluationContext quyết định SpEL được phép đọc hoặc ghi dữ liệu theo cách nào. Nếu use case chỉ cần đọc, hãy chọn context chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Context này phù hợp với các biểu thức data binding chỉ cần đọc property. Những thao tác ghi property thông qua data binding sẽ không được cho phép như ở context read-write.

Nếu thực sự cần cập nhật property qua SpEL, có thể sử dụng builder read-write:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Việc chọn read-write cần có chủ đích. Chỉ bật khả năng ghi cho luồng dữ liệu cần cập nhật, và nên giới hạn root object cũng như property accessor. Không nên cấp một context rộng chỉ để giải quyết một phép gán đơn giản.

Với **StandardEvaluationContext**, ứng dụng có thể cấu hình property accessor, method resolver, bean resolver và các thành phần khác. Khả năng rộng hơn cũng đồng nghĩa cần kiểm soát kỹ hơn những gì được expose cho biểu thức.

## Kiểm tra biểu thức có thể ghi hay không

Interface **Expression** cung cấp **isWritable(...)** để kiểm tra vị trí mà biểu thức trỏ tới có thể được cập nhật trong context và root object cụ thể hay không:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

if (nameExpression.isWritable(context, user)) {
    nameExpression.setValue(context, user, "Alex");
}
~~~

Ví dụ này kiểm tra property name có thể ghi trước khi gọi setValue. Cách làm hữu ích khi ứng dụng thao tác với property động hoặc cấu trúc object chưa biết hoàn toàn tại thời điểm biên dịch.

Tuy nhiên, isWritable chỉ phản ánh khả năng ghi theo accessor và context hiện tại. Nó không xác nhận người dùng có quyền cập nhật dữ liệu, không kiểm tra quy tắc chuyển trạng thái và không bảo đảm setter sẽ không tạo side effect. Validation nghiệp vụ vẫn cần được thực hiện ở lớp phù hợp.

## Tách thao tác đọc và cập nhật

Một thiết kế dễ hiểu là dùng biểu thức để đọc giá trị, sau đó để Java quyết định khi nào cập nhật:

~~~java
Expression statusExpression =
        parser.parseExpression("status");

String currentStatus =
        statusExpression.getValue(
                readOnlyContext, order, String.class);

if ("PENDING".equals(currentStatus)) {
    orderService.approve(order.getId());
}
~~~

Trong ví dụ này, biểu thức chỉ đọc trạng thái. Việc phê duyệt được chuyển cho service method, nơi có thể kiểm tra quyền, kiểm tra trạng thái hiện tại, áp dụng transaction và ghi audit.

Nếu cập nhật property đơn giản là một phần của data binding, có thể dùng **setValue(...)** với context read-write. Nhưng nếu thay đổi có ý nghĩa nghiệp vụ, hãy ưu tiên API Java có tên rõ ràng để thể hiện hành động và các điều kiện đi kèm.

## Những vị trí nên tránh biểu thức có phép gán

Tránh phép gán trong những biểu thức được thiết kế để đọc hoặc tính toán, ví dụ:

- Điều kiện kiểm tra quyền hoặc điều kiện quyết định có thực hiện một hành vi hay không.
- Biểu thức tạo cache key hoặc xác định giá trị cache.
- Biểu thức hiển thị dữ liệu trên giao diện.
- Cấu hình có thể được framework đánh giá nhiều lần hoặc trên nhiều request.
- Biểu thức lấy từ người dùng hoặc nguồn cấu hình không được kiểm soát.
- Biểu thức thao tác trên entity hoặc object được chia sẻ giữa nhiều thành phần.

Trong các vị trí này, side effect có thể làm thay đổi dữ liệu ngoài dự kiến, gây lỗi phụ thuộc thứ tự hoặc khiến cùng một điều kiện trả về kết quả khác nhau giữa các lần đánh giá.

## Nếu cần đánh giá biểu thức do bên ngoài cung cấp

Không nên cho phép một chuỗi SpEL tùy ý thao tác trên toàn bộ object graph của ứng dụng. Nếu người dùng hoặc hệ thống bên ngoài được phép cung cấp biểu thức, hãy giới hạn:

- **Root object:** dùng DTO nhỏ, chỉ chứa dữ liệu cần thiết.
- **Property access:** chỉ expose property nằm trong allowlist bằng accessor phù hợp.
- **Evaluation context:** dùng context chỉ đọc nếu use case chỉ cần truy xuất dữ liệu.
- **Method access:** không bật gọi phương thức nếu không có nhu cầu rõ ràng.
- **Nguồn và vòng đời biểu thức:** xác thực trước khi lưu, giới hạn độ dài và kiểm soát ai được phép thay đổi biểu thức.

Một context chỉ đọc không tự biến mọi object thành dữ liệu an toàn. Nếu root object chứa tham chiếu đến service hoặc object có hành vi phức tạp, vẫn cần giới hạn những gì biểu thức có thể truy cập.

## Kết luận

Phép gán trong SpEL có thể làm thay đổi trạng thái object ngay trong lúc evaluate. Tác động có thể đi qua setter, property lồng nhau, collection hoặc object được chia sẻ; setter còn có thể kích hoạt event và logic nghiệp vụ. Nếu object là entity đang được quản lý, thay đổi trong bộ nhớ có thể được ghi xuống database khi transaction flush hoặc commit.

Hãy giữ biểu thức chỉ đọc ở những nơi framework kỳ vọng truy xuất hoặc tính toán dữ liệu. Dùng context read-only khi phù hợp, kiểm tra khả năng ghi khi cần data binding và đưa các thay đổi nghiệp vụ vào service method có tên rõ ràng. Cách tổ chức này giúp side effect dễ nhận biết, dễ kiểm thử và dễ kiểm soát hơn.
