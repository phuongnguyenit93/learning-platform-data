# SimpleEvaluationContext với bề mặt thao tác giới hạn

**SimpleEvaluationContext** là một implementation của SpEL **EvaluationContext** được thiết kế cho những trường hợp chỉ cần một tập con khả năng của ngôn ngữ biểu thức. Thay vì mở toàn bộ cơ chế truy cập và thực thi mà một evaluation context tổng quát có thể cung cấp, ta chủ động chọn các khả năng cần thiết như đọc thuộc tính, chuyển đổi kiểu hoặc gọi instance method.

Mục tiêu là cung cấp môi trường đánh giá biểu thức gọn và dễ kiểm soát hơn, đặc biệt trong các tình huống data binding hoặc khi biểu thức không cần truy cập đến các thành phần rộng của ứng dụng.

## Vì sao cần một evaluation context giới hạn?

SpEL có thể làm nhiều việc hơn đọc một thuộc tính. Tùy cấu hình, biểu thức có thể gọi phương thức, tham chiếu kiểu Java, tạo object, truy cập bean hoặc sử dụng các cơ chế mở rộng. Những khả năng đó hữu ích trong cấu hình do lập trình viên kiểm soát, nhưng có thể vượt quá nhu cầu của một biểu thức chỉ dùng để đọc dữ liệu.

Ví dụ, một màn hình quản trị có thể cần biểu thức để hiển thị tên và trạng thái của một DTO. Nếu chỉ cần đọc các thuộc tính đó, việc cho biểu thức quyền gọi phương thức tùy ý, tạo object hoặc truy cập bean là không cần thiết.

**SimpleEvaluationContext** giải quyết vấn đề bằng cách để ứng dụng chọn một cấu hình giới hạn. Các tính năng bị loại khỏi context sẽ không khả dụng chỉ vì cú pháp SpEL có hỗ trợ chúng. Quyền thực tế của biểu thức phụ thuộc vào property accessor, method resolver, type converter và những thành phần được context cung cấp.

## SimpleEvaluationContext và StandardEvaluationContext

Hai lớp đều triển khai EvaluationContext, nhưng phục vụ phạm vi sử dụng khác nhau:

| Khía cạnh | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Mục đích | Đánh giá biểu thức với tập khả năng được giới hạn | Đánh giá biểu thức với khả năng mở rộng rộng hơn |
| Truy cập thuộc tính | Chọn property accessor; có builder dành cho data binding | Có thể cấu hình nhiều property accessor |
| Gọi instance method | Không bật mặc định; có thể bật rõ ràng bằng builder | Hỗ trợ cơ chế method resolver có thể cấu hình |
| Tham chiếu kiểu và constructor | Không cung cấp các cơ chế này | Có type locator và constructor resolver |
| Tham chiếu bean | Không cung cấp bean resolver mặc định | Có thể cấu hình bean resolver |
| Mức kiểm soát | Phù hợp khi muốn giới hạn bề mặt thao tác | Phù hợp khi cần tích hợp sâu và nhiều khả năng của SpEL |

Bảng trên mô tả định hướng thiết kế. Khả năng cuối cùng của một context còn phụ thuộc vào các thành phần được đăng ký và cách ứng dụng cấu hình chúng.

## Tạo SimpleEvaluationContext

Cách đơn giản nhất là dùng builder dành cho data binding chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Builder này cấu hình việc truy cập thuộc tính theo hướng chỉ đọc. Nó phù hợp khi biểu thức cần đọc các property JavaBean mà không cần thay đổi object.

Nếu use case cần cập nhật property thông qua biểu thức, có thể chọn builder đọc và ghi:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Việc chọn read-only hay read-write nên phản ánh đúng yêu cầu của tác vụ. Với biểu thức dùng để hiển thị hoặc kiểm tra dữ liệu, read-only thường là điểm bắt đầu hợp lý. Chỉ bật khả năng ghi khi ứng dụng thực sự cần biểu thức cập nhật object.

## Ví dụ: đọc thuộc tính của object

Giả sử ứng dụng có một đối tượng người dùng:

~~~java
public class UserProfile {
    private final String displayName;
    private final int age;

    public UserProfile(String displayName, int age) {
        this.displayName = displayName;
        this.age = age;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getAge() {
        return age;
    }
}
~~~

Ta muốn đánh giá một biểu thức kiểm tra độ tuổi và trả về tên hiển thị:

~~~java
UserProfile user = new UserProfile("An", 21);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "age >= 18 ? displayName : 'Chưa đủ tuổi'");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

String label = expression.getValue(context, user, String.class);
~~~

Ở đây, **user** được truyền làm root object cho lần đánh giá. Property accessor của data binding đọc các thuộc tính tương ứng thông qua getter. Biểu thức sử dụng phép so sánh và toán tử điều kiện để tạo kết quả chuỗi.

Cách gọi **getValue(context, user, String.class)** giúp chỉ rõ context, root object và kiểu kết quả mong muốn. Context có thể được tái sử dụng với các root object khác nhau nếu chúng phù hợp với những property mà biểu thức tham chiếu.

## Sử dụng biến trong biểu thức

Evaluation context cũng có thể chứa biến do ứng dụng cung cấp. Tên biến trong biểu thức được đặt sau dấu **#**:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumAge", 18);

Expression expression =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible =
        expression.getValue(context, user, Boolean.class);
~~~

Biến **minimumAge** không tự xuất hiện trong object. Ứng dụng chủ động đưa nó vào context bằng **setVariable**. Điều này giúp biểu thức nhận đúng dữ liệu cần thiết mà không phải thêm mọi giá trị vào root object.

Khi context được tái sử dụng, cần quản lý các biến theo từng lần đánh giá để tránh dùng nhầm dữ liệu của yêu cầu trước. Với ứng dụng đa luồng, nên chú ý vòng đời và phạm vi chia sẻ của context; không chia sẻ một context có trạng thái thay đổi giữa các yêu cầu nếu điều đó có thể làm lẫn biến hoặc dữ liệu đánh giá.

## Khi nào cần cho phép gọi instance method?

Mặc định, builder data binding của SimpleEvaluationContext không bật khả năng gọi instance method. Nếu một biểu thức thực sự cần gọi phương thức trên root object hoặc một property, có thể bật rõ ràng bằng **withInstanceMethods()**:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();

Expression expression =
        parser.parseExpression("displayName.toUpperCase()");

String normalizedName =
        expression.getValue(context, user, String.class);
~~~

Việc bật instance method làm bề mặt thao tác rộng hơn. Chỉ nên bật khi biểu thức cần đến phương thức cụ thể và các object được expose đã được kiểm soát. Không nên bật theo thói quen nếu việc đọc property đã đủ đáp ứng yêu cầu.

Cần phân biệt instance method với việc tham chiếu đến một kiểu Java hoặc gọi constructor. **withInstanceMethods()** chỉ mở khả năng gọi instance method theo cơ chế của context; nó không biến SimpleEvaluationContext thành StandardEvaluationContext và không bổ sung toàn bộ các tính năng như type reference, constructor hay bean reference.

## Chọn property accessor riêng

Hai builder data binding thuận tiện khi object tuân theo quy ước JavaBean. Nếu ứng dụng muốn giới hạn chính xác thuộc tính nào biểu thức được phép đọc hoặc ghi, có thể tạo context từ những **PropertyAccessor** được chỉ định:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(myPropertyAccessor)
                .build();
~~~

**PropertyAccessor** là thành phần SpEL dùng để đọc hoặc ghi một property trên target object. Một accessor tùy chỉnh có thể chỉ expose một số trường dữ liệu đã chọn, ánh xạ tên property biểu thức sang cấu trúc nội bộ hoặc áp dụng quy tắc truy cập riêng của ứng dụng.

Khi dùng accessor tùy chỉnh, cần xác định rõ nó hỗ trợ đọc hay ghi, loại target object nào và những tên property nào được chấp nhận. Không nên vô tình đăng ký accessor có khả năng truy cập rộng hơn yêu cầu. Nếu cần nhiều accessor, có thể truyền nhiều accessor vào factory method.

## Giới hạn không đồng nghĩa với sandbox tuyệt đối

SimpleEvaluationContext giúp thu hẹp khả năng mà biểu thức có thể sử dụng, nhưng bản thân việc chọn lớp context không đủ để bảo đảm an toàn cho mọi biểu thức bên ngoài.

Một context chỉ đọc vẫn có thể expose nhiều dữ liệu nếu root object có quá nhiều property. Khi bật instance method, biểu thức có thể gọi các phương thức được phép trên những object có thể truy cập. Một property accessor tùy chỉnh cũng có thể mở ra nhiều khả năng hơn dự định nếu được viết hoặc cấu hình không cẩn thận.

Nếu phải đánh giá biểu thức do người dùng hoặc hệ thống bên ngoài cung cấp, nên áp dụng các nguyên tắc sau:

- Dùng root object nhỏ, chỉ chứa dữ liệu cần thiết cho biểu thức; tránh đưa service, repository hoặc object quản lý tài nguyên vào context.
- Bắt đầu với **forReadOnlyDataBinding()** nếu chỉ cần đọc dữ liệu.
- Không bật **withInstanceMethods()** trừ khi có use case rõ ràng.
- Ưu tiên property accessor theo allowlist khi cần kiểm soát chính xác tên thuộc tính được expose.
- Chỉ cung cấp biến và dữ liệu mà biểu thức thực sự cần.
- Kiểm soát nguồn biểu thức, giới hạn độ phức tạp và xử lý lỗi parse hoặc evaluation như dữ liệu đầu vào có thể không hợp lệ.

SimpleEvaluationContext không tự giới hạn thời gian chạy hay độ dài biểu thức. Nếu biểu thức đến từ nguồn không đáng tin cậy, ứng dụng vẫn phải thiết kế giới hạn tài nguyên và chính sách xác thực phù hợp với môi trường thực thi.

## Khi nào nên chọn SimpleEvaluationContext?

Nên cân nhắc SimpleEvaluationContext khi:

- Biểu thức chỉ cần đọc hoặc cập nhật dữ liệu theo quy tắc data binding.
- Ứng dụng muốn cho phép cấu hình một số biểu thức đơn giản trên DTO hoặc object dữ liệu.
- Không cần tham chiếu kiểu Java, tạo object hoặc truy cập bean.
- Muốn bật instance method một cách có chủ đích thay vì mặc định cho phép mọi cơ chế mở rộng.
- Muốn tự định nghĩa property accessor để expose một bề mặt dữ liệu nhỏ.

Nếu use case cần bean reference, type reference, constructor invocation hoặc các method resolver tùy chỉnh, **StandardEvaluationContext** có thể phù hợp hơn. Khi đó, ứng dụng cần cấu hình rõ các thành phần được phép và kiểm soát nguồn biểu thức cẩn thận.

## Kết luận

SimpleEvaluationContext là lựa chọn dành cho những biểu thức SpEL cần một tập khả năng vừa đủ. Các builder như **forReadOnlyDataBinding()**, **forReadWriteDataBinding()** và **forPropertyAccessors(...)** cho phép ứng dụng chọn cách truy cập property; **withInstanceMethods()** mở thêm khả năng gọi phương thức khi thật sự cần.

Giới hạn bề mặt thao tác giúp biểu thức dễ kiểm soát hơn và tránh expose những tính năng không cần thiết. Tuy nhiên, mức an toàn thực tế vẫn phụ thuộc vào root object, accessor, biến và các khả năng mà ứng dụng chủ động cung cấp cho evaluation context.
