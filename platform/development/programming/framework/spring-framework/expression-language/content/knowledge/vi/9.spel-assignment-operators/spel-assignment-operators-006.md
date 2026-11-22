# Nguy cơ làm thay đổi trạng thái qua biểu thức

SpEL không chỉ đọc dữ liệu và tính toán giá trị. Ngôn ngữ này còn hỗ trợ **toán tử gán** để thay đổi property hoặc phần tử dữ liệu nếu evaluation context và đối tượng đích cho phép ghi. Vì vậy, một biểu thức nhìn giống như một điều kiện hoặc phép tính thông thường vẫn có thể tạo ra tác động phụ lên object trong lúc đánh giá.

Nguy cơ chính là người đọc có thể nghĩ rằng việc gọi **getValue(...)** chỉ lấy dữ liệu, trong khi biểu thức chứa phép gán lại làm thay đổi trạng thái. Nếu object được chia sẻ, được quản lý bởi framework hoặc được dùng ở nhiều bước xử lý, thay đổi đó có thể ảnh hưởng đến hành vi về sau.

## Toán tử gán trong SpEL

Toán tử **=** gán giá trị cho một property hoặc một vị trí có thể ghi. Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
        parser.parseExpression("name = 'Alex'");

assignment.getValue(context, user);
~~~

Nếu root object là user và property name có thể ghi thông qua property accessor, biểu thức sẽ gán giá trị **Alex** cho property đó. Việc đánh giá biểu thức vì thế làm thay đổi object trong bộ nhớ.

Có thể thực hiện thao tác tương tự thông qua API **setValue(...)**:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

nameExpression.setValue(context, user, "Alex");
~~~

Cách thứ hai thể hiện rõ ý định cập nhật: ứng dụng lấy một Expression trỏ đến property rồi gọi setValue với giá trị mới. Khi mục đích là thay đổi dữ liệu, API này thường dễ đọc và dễ tìm kiếm trong mã nguồn hơn việc giấu phép gán bên trong một biểu thức được gọi bằng getValue.

## getValue không phải lúc nào cũng chỉ đọc

Tên phương thức **getValue(...)** dễ khiến người đọc cho rằng nó chỉ quan sát trạng thái. Nhưng nếu chuỗi biểu thức chứa toán tử gán, việc đánh giá có thể thực hiện phép gán như một phần của quá trình tính biểu thức.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("status = 'APPROVED'");

expression.getValue(context, order);
~~~

Sau khi đánh giá, property status của order có thể đã thay đổi nếu context cho phép ghi và object hỗ trợ cập nhật property. Vì vậy, cần xem toàn bộ biểu thức trước khi dùng getValue trong một điểm tích hợp mà người đọc kỳ vọng chỉ có thao tác đọc.

Đặc biệt, biểu thức có thể được lưu trong file cấu hình hoặc database. Người duy trì ứng dụng có thể chỉ nhìn thấy một chuỗi SpEL mà không nhận ra rằng nó có khả năng thay đổi trạng thái. Nên đặt tên và tổ chức biểu thức sao cho mục đích đọc hay ghi được thể hiện rõ.

## Những nơi có thể phát sinh thay đổi trạng thái

Một phép gán trong SpEL có thể tác động đến nhiều loại dữ liệu, tùy property accessor và đối tượng đích:

- **JavaBean property:** gán vào property thông qua setter hoặc cơ chế truy cập tương ứng.
- **Property lồng nhau:** thay đổi một property ở sâu trong object graph, nếu các đối tượng trung gian tồn tại và có thể truy cập.
- **Phần tử collection hoặc array:** cập nhật phần tử tại vị trí có thể ghi nếu accessor hỗ trợ.
- **Dữ liệu do context expose:** thay đổi object được đưa vào làm root object hoặc thông qua một property được expose.

Ví dụ, biểu thức **address.city = 'Hanoi'** có thể thay đổi city của object address nằm trong root object. Biểu thức **items[0] = 'Updated'** có thể thay thế phần tử đầu tiên của một collection phù hợp. Các thao tác này phụ thuộc khả năng ghi của accessor và kiểu dữ liệu thực tế.

Không nên suy luận rằng mọi biểu thức đều có thể gán vào mọi property. Một property không có setter, một collection không hỗ trợ cập nhật hoặc một accessor chỉ đọc có thể khiến phép gán thất bại khi đánh giá.

## Setter có thể tạo thêm side effect

Thay đổi property không nhất thiết chỉ là thay một giá trị trong field. Setter của JavaBean có thể thực hiện thêm logic:

~~~java
public void setStatus(String status) {
    validateTransition(this.status, status);
    this.status = status;
    this.updatedAt = Instant.now();
    publishStatusChangedEvent();
}
~~~

Nếu SpEL gán vào property status thông qua setter này, toàn bộ logic bên trong setter có thể chạy. Điều đó có thể cập nhật timestamp, phát sự kiện, ghi log hoặc thực hiện một hành động khác.

Vì vậy, cần đánh giá tác động của setter chứ không chỉ nhìn vào tên property trong biểu thức. Một biểu thức gán ngắn có thể kích hoạt logic nghiệp vụ đáng kể. Nếu việc cập nhật trạng thái cần kiểm tra quyền, xác thực chuyển trạng thái hoặc phối hợp nhiều thao tác, nên gọi một phương thức nghiệp vụ có tên rõ ràng thay vì để biểu thức thực hiện gián tiếp.

## Lặp lại evaluation có thể lặp lại tác động phụ

Expression có thể được parse một lần rồi đánh giá nhiều lần. Nếu biểu thức chỉ đọc dữ liệu, việc đánh giá lặp lại thường không làm thay đổi object. Nhưng nếu biểu thức chứa phép gán, mỗi lần evaluate có thể thực hiện cập nhật một lần nữa.

Ngay cả khi gán cùng một giá trị, setter vẫn có thể chạy lại và tạo tác động phụ như cập nhật thời gian, phát event hoặc ghi audit. Do đó, không nên giả định một biểu thức gán là an toàn khi được gọi lặp lại.

Một điểm tích hợp của framework có thể đánh giá biểu thức trong những tình huống mà lập trình viên không trực tiếp gọi getValue ở nơi nhìn thấy được. Nếu biểu thức được dùng làm điều kiện, key hoặc cấu hình được đánh giá nhiều lần, việc có side effect sẽ làm hành vi khó dự đoán và khó kiểm thử.

## Ảnh hưởng đến object được chia sẻ và xử lý đồng thời

Root object có thể được nhiều thành phần trong ứng dụng cùng tham chiếu. Nếu một evaluation thay đổi object đó, những luồng hoặc yêu cầu khác có thể quan sát trạng thái mới.

Ví dụ, hai yêu cầu cùng sử dụng một object cấu hình hoặc một object nghiệp vụ đang được chia sẻ. Một biểu thức thay đổi property trong khi yêu cầu khác đang đọc property đó có thể tạo ra kết quả phụ thuộc thứ tự thực thi. Nếu nhiều luồng cùng cập nhật, ứng dụng còn phải xử lý vấn đề đồng bộ và tính nhất quán dữ liệu.

SpEL không tự thêm cơ chế khóa, transaction hay đồng bộ hóa cho object mà biểu thức thay đổi. Trách nhiệm quản lý trạng thái vẫn thuộc về ứng dụng. Không nên dùng biểu thức gán trên object chia sẻ nếu vòng đời, quyền ghi và quy tắc đồng thời chưa được xác định rõ.

## Thay đổi object trong bộ nhớ không đồng nghĩa với lưu dữ liệu

Phép gán của SpEL thay đổi object mà context đang truy cập. Nó không tự động mở transaction, gọi repository hoặc ghi dữ liệu xuống database.

Tuy nhiên, nếu object là entity đang được persistence context quản lý, thay đổi trong bộ nhớ có thể được persistence provider phát hiện và ghi xuống database khi transaction được flush hoặc commit theo quy tắc của framework. Vì thế, một phép gán tưởng như chỉ nằm trong biểu thức vẫn có thể gián tiếp ảnh hưởng đến dữ liệu bền vững.

Nếu cần thay đổi dữ liệu nghiệp vụ, hãy thực hiện trong service method có transaction boundary và quy tắc xác thực rõ ràng. Dùng SpEL để diễn đạt điều kiện hoặc truy cập dữ liệu thường dễ kiểm soát hơn dùng nó như cơ chế cập nhật entity.

## Giới hạn khả năng ghi bằng EvaluationContext

EvaluationContext quyết định biểu thức có thể truy cập và thao tác với object như thế nào. Với những use case chỉ cần đọc dữ liệu, có thể dùng **SimpleEvaluationContext.forReadOnlyDataBinding()**:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Context đọc dữ liệu này phù hợp cho biểu thức cần truy cập property mà không cần cập nhật object. Nếu biểu thức cố gắng thực hiện thao tác ghi không được hỗ trợ, evaluation sẽ thất bại thay vì thay đổi object qua cơ chế ghi thông thường của data binding.

Nếu ứng dụng cần ghi property, có thể chọn context read-write hoặc cấu hình property accessor phù hợp. Nhưng chỉ nên cấp quyền ghi cho biểu thức thực sự cần cập nhật và chỉ expose những property cần thiết.

Một context giới hạn không tự bảo đảm rằng toàn bộ object graph đều vô hại. Nếu root object chứa các tham chiếu đến service hoặc object có hành vi phức tạp, việc expose chúng vẫn có thể mở ra những tác động khác tùy khả năng được context hỗ trợ. Nên cung cấp DTO nhỏ và accessor theo allowlist khi đánh giá biểu thức bên ngoài.

## Kiểm tra khả năng ghi trước khi cập nhật

Expression cung cấp phương thức **isWritable(...)** để kiểm tra một biểu thức có thể ghi vào vị trí mà nó trỏ tới trong context và root object hiện tại hay không:

~~~java
Expression nameExpression =
        parser.parseExpression("name");

if (nameExpression.isWritable(context, user)) {
    nameExpression.setValue(context, user, "Alex");
}
~~~

Việc kiểm tra này hữu ích khi ứng dụng cần cập nhật property theo cấu trúc động. Tuy nhiên, isWritable chỉ xác định khả năng ghi theo accessor và context tại thời điểm kiểm tra. Nó không thay thế xác thực nghiệp vụ, kiểm tra quyền của người dùng, kiểm tra trạng thái hợp lệ hoặc bảo đảm thao tác sẽ thành công trong mọi điều kiện sau đó.

Nếu property không writable, không nên cố gắng bỏ qua giới hạn bằng cách chuyển sang một context có quyền rộng hơn mà không có lý do. Hãy xác định vì sao property không thể ghi và chọn API cập nhật phù hợp.

## Tách biểu thức đọc và biểu thức ghi

Một cách tổ chức dễ hiểu là giữ riêng biểu thức dùng để đọc với thao tác cập nhật:

~~~java
Expression statusExpression =
        parser.parseExpression("status");

String currentStatus =
        statusExpression.getValue(readOnlyContext, order, String.class);

// Quyết định nghiệp vụ được thực hiện rõ trong Java
if ("PENDING".equals(currentStatus)) {
    statusExpression.setValue(writeContext, order, "APPROVED");
}
~~~

Ví dụ này làm rõ hai bước: đọc trạng thái hiện tại và cập nhật khi điều kiện nghiệp vụ được đáp ứng. Trong ứng dụng thực tế, phần quyết định có thể cần gọi service method để kiểm tra quyền, kiểm tra chuyển trạng thái và phối hợp các thao tác khác.

Việc tách đọc và ghi cũng giúp tìm kiếm các điểm mutation trong mã nguồn dễ hơn. Khi cần kiểm thử, có thể xác nhận phần đọc không làm thay đổi object và phần ghi chỉ xảy ra trong điều kiện đã xác định.

## Những trường hợp nên tránh phép gán trong biểu thức

Không nên đưa phép gán vào biểu thức khi điểm tích hợp được thiết kế để đọc hoặc tính toán một giá trị, chẳng hạn:

- Điều kiện kiểm tra quyền hoặc điều kiện bật/tắt hành vi.
- Biểu thức tạo cache key.
- Biểu thức chỉ dùng để hiển thị dữ liệu.
- Cấu hình được framework đánh giá nhiều lần hoặc trong nhiều ngữ cảnh.
- Biểu thức lấy từ người dùng hoặc nguồn cấu hình không đáng tin cậy.
- Root object được chia sẻ giữa nhiều yêu cầu hoặc được quản lý bởi persistence context.

Trong các trường hợp này, một biểu thức có side effect có thể làm thay đổi kết quả của những bước khác, khiến lỗi khó tái hiện và tạo ra thay đổi dữ liệu ngoài dự kiến. Hãy giữ biểu thức chỉ đọc và đưa thao tác cập nhật vào Java nếu có thể.

## Khi nào phép gán trong SpEL có thể phù hợp?

Toán tử gán vẫn có ích trong một số tình huống có phạm vi rõ ràng, chẳng hạn binding dữ liệu vào một object tạm thời, cập nhật một DTO trong bước chuyển đổi hoặc thực hiện một thao tác cấu hình có kiểm soát.

Khi dùng, nên bảo đảm:

- Root object có vòng đời và quyền sở hữu rõ ràng.
- Property được phép ghi đã được xác định.
- Setter không tạo side effect ngoài dự kiến.
- Biểu thức không bị đánh giá lặp lại ngoài ý muốn.
- Có kiểm tra và xử lý lỗi evaluation.
- Quy tắc nghiệp vụ quan trọng vẫn được thực thi trong lớp Java phù hợp.

Nếu biểu thức được cấu hình bên ngoài mã nguồn, cần giới hạn root object, biến và property accessor. Không nên cung cấp một object có quyền truy cập rộng cho một chuỗi biểu thức không được kiểm soát.

## Kết luận

SpEL hỗ trợ phép gán, vì vậy việc đánh giá biểu thức có thể làm thay đổi trạng thái object. Tác động có thể đi qua setter, property lồng nhau hoặc phần tử collection; setter còn có thể kích hoạt event, cập nhật timestamp hoặc thực hiện logic khác. Thay đổi trong bộ nhớ cũng có thể được persistence context ghi nhận nếu object đang được quản lý.

Hãy dùng context chỉ đọc cho biểu thức chỉ cần quan sát dữ liệu, kiểm tra khả năng ghi khi cập nhật property và tách rõ biểu thức đọc với thao tác ghi. Với thay đổi nghiệp vụ, ưu tiên service method có tên rõ ràng để quyền, validation và transaction được kiểm soát ở đúng nơi.
