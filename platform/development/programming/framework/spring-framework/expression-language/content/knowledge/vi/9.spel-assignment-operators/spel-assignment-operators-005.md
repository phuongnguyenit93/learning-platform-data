# Phân biệt gán trong SpEL với bind dữ liệu của framework

SpEL có toán tử gán để thay đổi giá trị của thuộc tính trong đối tượng mà biểu thức đang truy cập. Spring cũng có cơ chế data binding để đưa dữ liệu đầu vào, chẳng hạn request parameter hoặc form field, vào các thuộc tính của một object. Hai việc này đều có thể làm thay đổi object, nhưng chúng khác nhau về mục đích, thời điểm chạy, cách kiểm soát và trách nhiệm xử lý dữ liệu.

Gán trong SpEL là một hành động xảy ra khi một biểu thức được đánh giá trong EvaluationContext. Data binding là một quy trình của framework: framework nhận dữ liệu đầu vào, ánh xạ tên field vào property, chuyển đổi kiểu, áp dụng quy tắc binding và có thể chạy validation. Không nên xem hai cơ chế là thay thế cho nhau.

## 1. Toán tử gán trong SpEL

SpEL dùng dấu bằng đơn để gán giá trị:

~~~text
name = 'Lan'
quantity = 3
address.city = 'Ho Chi Minh City'
~~~

Khi biểu thức được đánh giá, SpEL tìm thuộc tính đích thông qua cơ chế truy cập property của EvaluationContext rồi ghi giá trị mới vào thuộc tính đó. Đối tượng cần thay đổi thường là root object hoặc một object có thể truy cập từ root object.

Ví dụ với một bean Java:

~~~java
public class Profile {

    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Có thể gán thuộc tính bằng biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

Expression assignment = parser.parseExpression(
        "displayName = 'Lan'"
);

assignment.getValue(context);

System.out.println(profile.getDisplayName()); // Lan
~~~

Lệnh parseExpression chỉ phân tích chuỗi và tạo Expression. Việc thay đổi object xảy ra khi gọi getValue với context, vì lúc đó biểu thức mới được đánh giá. Nếu chỉ parse mà không đánh giá, thuộc tính chưa bị thay đổi.

Điều kiện để phép gán thành công là property đích phải có thể ghi qua accessor mà context đang sử dụng. Nếu thuộc tính không tồn tại, không có setter phù hợp hoặc accessor chỉ cho phép đọc, SpEL sẽ không thể thực hiện phép gán đó.

## 2. Gán thuộc tính lồng nhau

Một biểu thức có thể truy cập thuộc tính lồng nhau rồi gán vào thuộc tính ở object con:

~~~java
Expression assignment = parser.parseExpression(
        "address.city = 'Ho Chi Minh City'"
);

assignment.getValue(context);
~~~

Đường dẫn address.city yêu cầu root object có thuộc tính address và object được trả về có thuộc tính city có thể ghi. Nếu một mắt xích trong đường dẫn là null hoặc không thể truy cập, phép gán có thể thất bại.

Khi gán vào object lồng nhau, cần chú ý rằng biểu thức có thể thay đổi trực tiếp trạng thái của object con được tham chiếu. Nếu object đó được chia sẻ ở nhiều nơi, thay đổi có thể được quan sát bởi những đoạn code khác đang giữ cùng reference.

Không nên truyền một object graph quá rộng vào context chỉ để thuận tiện cho một phép gán. Hãy chọn root object có phạm vi nhỏ và chỉ chứa những property mà biểu thức thực sự cần thay đổi.

## 3. Phân biệt dấu bằng gán với dấu bằng so sánh

Trong SpEL, dấu bằng đơn và dấu bằng kép có ý nghĩa khác nhau:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| = | Gán giá trị | name = 'Lan' |
| == | So sánh bằng | name == 'Lan' |
| != | So sánh khác | status != 'DISABLED' |

Ví dụ:

~~~text
status = 'ACTIVE'
~~~

Biểu thức này ghi giá trị ACTIVE vào property status nếu property có thể ghi.

Trong khi đó:

~~~text
status == 'ACTIVE'
~~~

chỉ kiểm tra status có bằng ACTIVE hay không và trả về kết quả Boolean. Nó không thay đổi property.

Nhầm lẫn giữa = và == có thể dẫn đến side effect ngoài ý muốn. Khi viết biểu thức điều kiện, hãy dùng toán tử so sánh. Chỉ dùng dấu bằng đơn khi thật sự muốn cập nhật dữ liệu trong lúc đánh giá.

## 4. Dùng Expression.setValue để ghi property

SpEL còn cung cấp API setValue trên Expression. API này phù hợp khi biểu thức chỉ mô tả đường dẫn tới property cần ghi:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
EvaluationContext context =
        new StandardEvaluationContext(profile);

Expression displayName = parser.parseExpression("displayName");

displayName.setValue(context, "Minh");

System.out.println(profile.getDisplayName()); // Minh
~~~

Ở đây chuỗi displayName chỉ định property đích. Giá trị được truyền riêng vào setValue, nên không cần nhúng giá trị mới vào chuỗi biểu thức.

Có thể dùng cùng cách cho property lồng nhau:

~~~java
Expression city = parser.parseExpression("address.city");
city.setValue(context, "Da Nang");
~~~

Cả toán tử gán trong biểu thức và Expression.setValue đều có thể làm thay đổi object. Khác biệt chính nằm ở cách biểu đạt:

- Toán tử = đặt cả property đích và giá trị cần gán trong nội dung SpEL.
- setValue tách biểu thức đường dẫn property khỏi giá trị mới được truyền bằng Java.

Nếu ứng dụng đã có giá trị trong Java và chỉ cần ghi vào một property, setValue thường giúp ranh giới dữ liệu rõ hơn. Nếu đang xây dựng một biểu thức có mục tiêu cập nhật được mô tả trong chính rule, toán tử gán có thể phù hợp, nhưng cần kiểm soát rõ context và nguồn biểu thức.

## 5. EvaluationContext quyết định property có thể ghi hay không

Khả năng đọc và ghi property phụ thuộc vào property accessor mà EvaluationContext cung cấp.

### 5.1. StandardEvaluationContext

StandardEvaluationContext hỗ trợ cấu hình root object, biến, hàm, property accessor và các resolver khác. Các property accessor mặc định dùng reflection để truy cập property Java phù hợp, bao gồm khả năng ghi nếu property hỗ trợ.

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

parser.parseExpression("displayName = 'Lan'")
        .getValue(context);
~~~

Context này có phạm vi tính năng rộng. Nếu biểu thức không đáng tin cậy, việc cho phép nó truy cập một object lớn hoặc các method có tác dụng phụ có thể mở rộng quyền của biểu thức vượt quá mục đích ban đầu.

### 5.2. SimpleEvaluationContext chỉ đọc

Nếu chỉ cần đọc dữ liệu, có thể dùng:

~~~java
EvaluationContext readOnly =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Context chỉ đọc phù hợp với biểu thức lọc hoặc hiển thị dữ liệu. Không nên kỳ vọng phép gán property hoạt động trong context này vì accessor được cấu hình cho mục đích đọc.

### 5.3. SimpleEvaluationContext đọc/ghi

Khi use case thật sự cần data binding theo tập tính năng giới hạn, có thể dùng:

~~~java
EvaluationContext readWrite =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

Context này dùng property accessor dành cho data binding và cho phép ghi property theo phạm vi mà accessor hỗ trợ. Đây vẫn là EvaluationContext để SpEL đánh giá biểu thức.

Tên forReadWriteDataBinding có thể khiến người đọc liên tưởng đến WebDataBinder hoặc DataBinder của Spring MVC. Tuy nhiên, builder này chỉ tạo một context SpEL với cấu hình truy cập property phù hợp; nó không tự nhận request, ánh xạ form field, tạo BindingResult hoặc chạy toàn bộ quy trình validation của MVC.

## 6. Data binding của Spring Framework là một quy trình riêng

Data binding đưa dữ liệu bên ngoài vào object đích dựa trên tên property. Một nguồn dữ liệu có thể là request parameter, form submission, map giá trị hoặc một cấu trúc dữ liệu do ứng dụng cung cấp.

Trong Spring MVC, WebDataBinder hỗ trợ bind request data vào model attribute. Framework thường thực hiện các bước như:

1. Nhận dữ liệu đầu vào từ request hoặc nguồn binding.
2. Xác định property đích dựa trên tên field.
3. Chuyển đổi giá trị văn bản sang kiểu Java cần thiết.
4. Áp dụng quy tắc allowed/disallowed fields và cấu hình binder.
5. Ghi giá trị vào object đích nếu binding thành công.
6. Thu thập lỗi binding và kết quả validation để controller xử lý.

Ví dụ một form object:

~~~java
public class ProfileForm {

    private String displayName;
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Spring MVC có thể bind các request parameter displayName và age vào ProfileForm khi xử lý một model attribute. Giá trị age ban đầu thường đến từ HTTP dưới dạng chuỗi; binder và conversion service chịu trách nhiệm chuyển nó sang Integer.

Không cần viết một biểu thức SpEL như age = ... để framework thực hiện việc binding đó. Binding là một phần của quy trình xử lý request của Spring MVC.

## 7. Ví dụ WebDataBinder và validation

Trong controller, có thể cấu hình WebDataBinder để giới hạn field được phép bind:

~~~java
@Controller
public class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping("/profile")
    public String update(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "profile-edit";
        }

        return "profile-result";
    }
}
~~~

Trong ví dụ, binder chỉ cho phép hai field được chỉ định. Các lỗi chuyển đổi hoặc validation được phản ánh trong BindingResult để controller quyết định cách phản hồi.

Đây là trách nhiệm mà một phép gán SpEL đơn lẻ không tự cung cấp. SpEL có thể ghi property nếu context cho phép, nhưng nó không tự động áp dụng allowed fields, kiểm tra annotation validation, tạo BindingResult hoặc điều phối response HTTP.

Đối với dữ liệu nhạy cảm, hãy dùng form/DTO riêng và giới hạn field được bind. Không nên bind trực tiếp mọi request field vào một entity có nhiều property nội bộ như role, status, ownerId hoặc permission flags.

## 8. So sánh SpEL assignment với framework data binding

| Khía cạnh | Gán trong SpEL | Spring DataBinder/WebDataBinder |
|---|---|---|
| Mục đích | Cập nhật property như một phần của biểu thức | Ánh xạ dữ liệu đầu vào vào object |
| Cách kích hoạt | Đánh giá Expression hoặc gọi Expression.setValue | Framework hoặc ứng dụng gọi quy trình bind |
| Nguồn giá trị | Literal, biến, root object hoặc kết quả biểu thức | Request parameter, form data, property values hoặc nguồn binding |
| Đường dẫn property | Do biểu thức SpEL chỉ định | Do tên field/property trong dữ liệu binding xác định |
| Chuyển đổi kiểu | Theo TypeConverter của EvaluationContext | Theo conversion/property editor và cấu hình binder |
| Validation | Không tự chạy validation của bean | Có thể kết hợp Validator và Bean Validation |
| Kiểm soát field | Qua accessor và cấu hình context | Qua allowed/disallowed fields và cấu hình binder |
| Lỗi | Thường xuất hiện khi đánh giá hoặc ghi property | Được thu thập trong BindingResult khi dùng MVC |
| Phạm vi | Một biểu thức cụ thể | Quy trình binding của framework |

Hai cơ chế có thể cùng làm thay đổi một object, nhưng không nên dùng một phép gán SpEL để thay thế quy trình binding của MVC. Ngược lại, DataBinder không phải parser để đánh giá một biểu thức SpEL bất kỳ.

## 9. Chuyển đổi kiểu không đồng nghĩa với validation

Khi gán property bằng SpEL, TypeConverter của EvaluationContext có thể chuyển đổi giá trị nếu cần và nếu converter hỗ trợ. Ví dụ, giá trị biểu thức có thể được chuyển sang kiểu của property đích.

DataBinder cũng có cơ chế chuyển đổi kiểu, nhưng nó còn có thể ghi nhận lỗi binding và kết hợp validation. Hai cơ chế có thể cùng dùng các thành phần chuyển đổi của Spring, nhưng quy trình xử lý lỗi và kiểm tra nghiệp vụ không giống nhau.

Hãy phân biệt ba việc:

- Conversion: biến đổi giá trị từ kiểu nguồn sang kiểu đích.
- Binding: ánh xạ giá trị nguồn vào property cụ thể của object.
- Validation: kiểm tra object hoặc field có thỏa mãn quy tắc nghiệp vụ hay không.

Một phép gán thành công không chứng minh object hợp lệ. Ví dụ, gán age = -5 có thể thành công nếu property là Integer, nhưng dữ liệu vẫn có thể vi phạm quy tắc tuổi của ứng dụng. Validation cần được thực hiện rõ ràng sau khi dữ liệu được cập nhật.

## 10. Tác dụng phụ và quyền ghi

Gán trong SpEL là một hành động thay đổi trạng thái. Nếu biểu thức được đánh giá nhiều lần, cùng một phép gán có thể được thực hiện nhiều lần. Nếu root object được chia sẻ, thay đổi có thể ảnh hưởng đến nơi khác đang dùng object đó.

Ví dụ:

~~~text
account.balance = 0
~~~

Nếu context cho phép ghi, biểu thức có thể thay đổi balance ngay khi được đánh giá. Đây không phải một phép kiểm tra thuần túy.

Với biểu thức lấy từ cấu hình có thể chỉnh sửa hoặc từ người dùng, cần giới hạn:

1. Root object chỉ chứa những property cần thiết.
2. Property accessor chỉ cho phép các thao tác cần dùng.
3. Không cấp object chứa service/repository có khả năng ghi dữ liệu nếu không cần.
4. Ưu tiên context chỉ đọc cho biểu thức lọc và hiển thị.
5. Không dùng biểu thức do người dùng cung cấp để cập nhật entity trực tiếp.
6. Thực hiện authorization và validation trong application/service layer trước khi lưu thay đổi.

Nếu cần cập nhật dữ liệu theo request, dùng DTO, binder được cấu hình và validation phù hợp. Nếu cần tính toán hoặc gán một giá trị trong một rule nội bộ đã kiểm soát, SpEL assignment có thể được dùng với context có phạm vi rõ ràng.

## 11. Khi nào nên dùng từng cách?

### Dùng SpEL assignment khi

- Biểu thức nội bộ cần cập nhật một property cụ thể trong object đã được cấp.
- Giá trị gán được xác định bởi chính biểu thức.
- Context và property accessor được kiểm soát.
- Không cần quy trình request binding hoặc validation đầy đủ.

Ví dụ:

~~~java
Expression assignment = parser.parseExpression(
        "displayName = #normalizedName"
);

StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

context.setVariable("normalizedName", "Lan Nguyen");

assignment.getValue(context);
~~~

### Dùng Expression.setValue khi

- Java đã có giá trị mới và chỉ cần ghi vào property path.
- Muốn tách giá trị dữ liệu khỏi chuỗi expression.
- Cần dùng một API biểu đạt rõ thao tác ghi property.

~~~java
parser.parseExpression("displayName")
        .setValue(context, normalizedName);
~~~

### Dùng DataBinder hoặc WebDataBinder khi

- Dữ liệu đến từ HTTP form, request parameter hoặc một nguồn binding.
- Cần chuyển đổi kiểu theo field.
- Cần giới hạn field được bind.
- Cần thu thập lỗi binding và kết hợp validation.
- Cần tuân theo lifecycle xử lý request của Spring MVC.

Hãy chọn cơ chế theo nguồn dữ liệu và trách nhiệm của tầng ứng dụng, không chỉ dựa trên việc cả hai đều có thể gọi setter.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gán SpEL không thay đổi property | Chỉ parse expression mà chưa đánh giá | Gọi getValue(context) hoặc setValue(context, value) |
| Gặp lỗi không thể ghi property | Property không có setter hoặc accessor chỉ đọc | Kiểm tra property accessor và context |
| Dùng dấu = nhưng muốn so sánh | Nhầm assignment với equality | Dùng == cho phép so sánh |
| SimpleEvaluationContext không cho phép ghi | Đang dùng builder read-only | Chỉ dùng forReadWriteDataBinding khi thật sự cần ghi |
| Nghĩ SpEL tự chạy Bean Validation | Nhầm phép gán với quy trình binding | Gọi validation trong application flow |
| Request field không được cập nhật | Binder không cho phép field hoặc tên field không khớp | Kiểm tra allowed fields và tên property |
| Dữ liệu ngoài sửa được field nhạy cảm | Bind trực tiếp vào object có quá nhiều property | Dùng form DTO và allowlist field |
| Gán thành công nhưng dữ liệu không hợp lệ | Conversion không đồng nghĩa với validation | Validate object sau khi cập nhật |

## 13. Ghi nhớ

Toán tử = trong SpEL ghi giá trị vào property khi biểu thức được đánh giá và EvaluationContext cho phép ghi. Expression.setValue cũng ghi property nhưng tách đường dẫn property khỏi giá trị mới. Dấu == dùng để so sánh và không thay đổi object.

DataBinder/WebDataBinder là quy trình binding của Spring: nhận dữ liệu nguồn, ánh xạ property, chuyển đổi kiểu, kiểm soát field và có thể kết hợp validation. SimpleEvaluationContext.forReadWriteDataBinding() vẫn chỉ là cách cấu hình property access cho một SpEL EvaluationContext, không phải quy trình WebDataBinder.

Hãy dùng SpEL assignment cho những cập nhật biểu thức nhỏ, có kiểm soát. Dùng DataBinder/WebDataBinder cho dữ liệu đầu vào cần binding, lỗi và validation. Với mọi thao tác ghi, hãy xác định rõ object nào bị thay đổi, ai được phép thay đổi và validation được thực hiện ở đâu.