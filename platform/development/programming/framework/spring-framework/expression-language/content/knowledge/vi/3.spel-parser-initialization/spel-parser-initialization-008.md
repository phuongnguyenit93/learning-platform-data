# Auto grow null references và auto grow collections trong SpEL

SpEL có thể tự khởi tạo một thuộc tính đang là null và tự mở rộng collection khi biểu thức truy cập một index nằm ngoài kích thước hiện tại. Hai khả năng này thường được gọi là **auto grow null references** và **auto grow collections**. Chúng giúp cập nhật object graph bằng một biểu thức ngắn, nhưng cũng có thể làm thay đổi dữ liệu trong lúc đánh giá biểu thức.

Bài học này giải thích cách bật hai khả năng trong SpelParserConfiguration, cách chúng phối hợp khi truy cập thuộc tính lồng nhau trong List, cách giới hạn kích thước tăng và các trường hợp nên tránh.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt tự khởi tạo thuộc tính null với tự mở rộng collection.
- Cấu hình hai hành vi độc lập bằng SpelParserConfiguration.
- Dùng Expression.setValue(...) để cập nhật một property path có object trung gian đang null.
- Mở rộng List tới index cần thiết và khởi tạo phần tử nếu kiểu phần tử có thể xác định.
- Đặt giới hạn tăng trưởng và dự đoán các lỗi khi vượt giới hạn hoặc thiếu thông tin kiểu.
- Nhận biết side effect, ảnh hưởng tới dữ liệu và rủi ro khi đánh giá biểu thức không tin cậy.

Bạn nên biết Java class, getter/setter, constructor, List và cách dùng SpelExpressionParser để parse một biểu thức. Bài này tập trung vào cấu hình parser và hành vi khi đánh giá, không đi sâu toàn bộ cú pháp SpEL.

## 2. Hai cơ chế giải quyết hai tình huống khác nhau

Hãy tưởng tượng một object có cấu trúc:

~~~java
class Person {
    private Address address;
    // getter và setter
}

class Address {
    private String city;
    // getter và setter
}
~~~

Nếu person.getAddress() đang là null, biểu thức address.city không thể đi tiếp theo cách truy cập thuộc tính thông thường. Auto grow null references cho phép SpEL tạo object trung gian khi parser được cấu hình để làm việc đó và kiểu đích có thể khởi tạo.

Tình huống thứ hai là một danh sách:

~~~java
class Order {
    private List<LineItem> items = new ArrayList<>();
    // getter và setter
}
~~~

Nếu items đang rỗng mà biểu thức truy cập items[2], index 2 chưa tồn tại. Auto grow collections cho phép SpEL mở rộng collection để index đó có thể được truy cập.

Hai hành vi có thể bật độc lập:

| Cấu hình | Tác dụng |
|---|---|
| Auto grow null references | Khởi tạo thuộc tính trung gian đang null khi SpEL có đủ thông tin kiểu và có thể tạo instance |
| Auto grow collections | Mở rộng collection được truy cập theo index vượt quá kích thước hiện tại, trong giới hạn cấu hình |

Nếu biểu thức là items[2].sku, cả hai khả năng có thể cùng cần thiết: collection phải tăng kích thước để có index 2, sau đó phần tử tại index 2 phải được khởi tạo nếu nó đang null để SpEL truy cập được sku.

## 3. Cấu hình bằng SpelParserConfiguration

Hai hành vi được điều khiển tại thời điểm tạo parser:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Hai tham số boolean lần lượt là:

1. autoGrowNullReferences: bật tự khởi tạo null reference trong property path.
2. autoGrowCollections: bật tự mở rộng collection khi truy cập index vượt kích thước.

Có thể đặt giới hạn kích thước tăng trưởng bằng constructor có tham số thứ ba:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, 64);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Trong ví dụ này, 64 là giới hạn auto-grow được cấu hình cho parser. Khi ứng dụng có dữ liệu đầu vào thay đổi, nên đặt giới hạn tường minh theo nhu cầu thay vì để biểu thức có thể yêu cầu một kích thước tùy ý.

Cấu hình được gắn với parser được tạo từ nó. Nếu tạo parser khác bằng cấu hình mặc định, không nên giả định parser đó có cùng hành vi auto-grow. Hãy quản lý parser và cấu hình ở nơi dễ kiểm soát, đồng thời tránh tạo parser với các quyền khác nhau một cách tùy tiện.

## 4. Auto grow null references: khởi tạo thuộc tính trung gian

### 4.1. Cơ chế hoạt động

Khi SpEL đi qua một property path có thuộc tính trung gian là null, parser bật auto grow null references có thể yêu cầu tạo instance cho thuộc tính đó rồi tiếp tục truy cập đường dẫn.

Ví dụ:

~~~java
Person person = new Person(); // address ban đầu là null

ExpressionParser parser =
    new SpelExpressionParser(
        new SpelParserConfiguration(true, false));

Expression expression = parser.parseExpression("address.city");
expression.setValue(person, "Ha Noi");
~~~

Sau khi đánh giá thành công, object graph có thể có dạng:

~~~text
person
  └── address
        └── city = "Ha Noi"
~~~

SpEL cần xác định được kiểu của thuộc tính để tạo object phù hợp. Vì vậy, class và property cần cung cấp metadata kiểu đủ rõ ràng. Kiểu cụ thể có constructor phù hợp thường dễ khởi tạo hơn interface, abstract class hoặc kiểu không thể tạo instance. Nếu không thể tạo object trung gian, biểu thức sẽ không thể tự hoàn tất đường dẫn.

### 4.2. Những điều kiện cần kiểm tra

- Property path phải đi qua một thuộc tính mà SpEL có thể nhận diện.
- Kiểu của thuộc tính null phải xác định được.
- Kiểu đó phải có khả năng được khởi tạo trong môi trường chạy.
- Property accessor phải có quyền truy cập cần thiết; với JavaBean thông thường, hãy cung cấp getter/setter phù hợp.
- Nếu có nhiều tầng null, từng tầng cần có khả năng được tạo để SpEL đi tiếp.

Auto grow không tự sửa mọi loại lỗi dữ liệu. Nó không thể suy ra một implementation tùy ý cho interface, không thể tạo một đối tượng nếu constructor cần tham số mà không có cơ chế cung cấp tham số, và không thay thế validation nghiệp vụ.

## 5. Auto grow collections: mở rộng theo index

### 5.1. Cơ chế hoạt động

Với collection truy cập bằng index, auto grow collections cho phép SpEL mở rộng collection khi index yêu cầu nằm ngoài kích thước hiện tại.

Ví dụ, nếu items là List rỗng, truy cập index 2 cần collection có đủ vị trí tới index đó. Những vị trí được tạo thêm có thể chứa null cho tới khi một biểu thức khác gán giá trị hoặc auto grow null references khởi tạo phần tử cần truy cập.

~~~java
Order order = new Order(); // items là List rỗng

ExpressionParser parser =
    new SpelExpressionParser(
        new SpelParserConfiguration(false, true, 64));

Expression expression = parser.parseExpression("items[2]");
expression.setValue(order, new LineItem());
~~~

Sau thao tác, List có thể chứa ba vị trí: index 0, index 1 và index 2. Phần tử mới được gán tại index 2; các vị trí trước đó được thêm vào để đáp ứng index.

### 5.2. Kết hợp với auto grow null references

Một ví dụ thực tế hơn là cập nhật thuộc tính của phần tử ở một index chưa tồn tại:

~~~java
class LineItem {
    private String sku;

    public LineItem() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }
}

class Order {
    private List<LineItem> items = new ArrayList<>();

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }
}
~~~

Cấu hình và đánh giá:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, 64);

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Order order = new Order();

Expression expression =
    parser.parseExpression("items[2].sku");

expression.setValue(order, "SKU-003");
~~~

Để biểu thức hoàn tất, SpEL cần xử lý hai bước: mở rộng List để có index 2, sau đó khởi tạo phần tử tại index đó nếu phần tử đang null và kiểu phần tử có thể xác định. Metadata kiểu generic như List<LineItem> giúp SpEL biết kiểu phần tử cần tạo. Nếu dùng collection raw hoặc khai báo phần tử bằng kiểu quá tổng quát, SpEL có thể không đủ thông tin để tự khởi tạo phần tử lồng nhau.

### 5.3. Collection nào phù hợp?

Auto grow có ý nghĩa rõ nhất với cấu trúc truy cập theo index như List. Map được truy cập theo key, không có khái niệm index cuối danh sách để tự mở rộng; việc một key chưa tồn tại không đồng nghĩa SpEL sẽ tự tạo value có kiểu mong muốn. Set cũng không cung cấp index để mở rộng theo cách này.

Với array, kích thước của Java array là cố định. Nếu use case cần tăng số phần tử thường xuyên, List thường là lựa chọn dễ hiểu và phù hợp hơn. Không nên giả định mọi kiểu collection đều có thể auto-grow giống nhau; hãy kiểm tra loại property và accessor thực tế của ứng dụng.

## 6. Hai tùy chọn phối hợp như thế nào?

Bảng sau mô tả kết quả thường gặp khi biểu thức cần truy cập items[2].sku và List ban đầu rỗng:

| Auto grow null references | Auto grow collections | Hành vi |
|---|---|---|
| Tắt | Tắt | Không tự tạo vị trí hoặc object; truy cập index ngoài phạm vi thất bại |
| Bật | Tắt | Không thể đi tới index chưa tồn tại; bật khởi tạo null không thay thế việc mở rộng List |
| Tắt | Bật | List có thể được mở rộng, nhưng phần tử null tại index 2 không tự được khởi tạo để truy cập sku |
| Bật | Bật | List có thể được mở rộng và phần tử null có thể được khởi tạo nếu SpEL xác định được kiểu phần tử |

Đây là hai cờ độc lập. Bật một cờ không tự động bật cờ còn lại.

## 7. Giới hạn kích thước và tác động tới bộ nhớ

Auto grow collections có thể làm tăng kích thước dữ liệu chỉ vì một biểu thức truy cập index lớn. Nếu index đến từ dữ liệu ngoài hệ thống, một giá trị rất lớn có thể khiến ứng dụng cấp phát nhiều phần tử hoặc tiêu tốn tài nguyên không cần thiết.

Hãy đặt maximumAutoGrowSize phù hợp:

~~~java
int maximumSize = 64;

SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, maximumSize);
~~~

Giới hạn này giúp chặn yêu cầu tăng trưởng vượt quá mức ứng dụng cho phép. Khi index hoặc kích thước yêu cầu vượt giới hạn, quá trình đánh giá có thể phát sinh exception. Ứng dụng cần xử lý lỗi đó như một đầu vào không hợp lệ hoặc một vi phạm giới hạn nghiệp vụ, tùy nguồn biểu thức.

Không dùng giới hạn kích thước thay cho validation. Nếu nghiệp vụ chỉ cho phép tối đa 10 dòng đơn hàng, hãy xác thực giới hạn 10 ở tầng nghiệp vụ; parser cap là lớp bảo vệ bổ sung cho hành vi auto-grow.

## 8. Auto grow có thể làm thay đổi trạng thái object

Điểm cần chú ý là auto grow là một hành vi có side effect. Khi đánh giá property path, SpEL có thể khởi tạo object hoặc mở rộng collection để tiếp tục truy cập. Vì vậy, không nên mặc định rằng mọi lời gọi getValue đều chỉ đọc dữ liệu và không thay đổi object graph khi parser đã bật auto-grow.

Hãy cân nhắc:

- Dùng object riêng cho thao tác binding hoặc cập nhật thay vì chia sẻ object mutable giữa nhiều request.
- Tránh đánh giá biểu thức có auto-grow trên object singleton hoặc object đang được nhiều luồng cùng sử dụng.
- Xác định rõ thời điểm object được phép thay đổi và ai chịu trách nhiệm lưu thay đổi đó.
- Nếu chỉ cần kiểm tra điều kiện, hãy dùng dữ liệu đã được khởi tạo đầy đủ và không bật auto-grow nếu không cần.
- Kiểm thử trạng thái trước và sau khi đánh giá để phát hiện thay đổi ngoài dự kiến.

## 9. An toàn khi đánh giá biểu thức

Auto grow không phải là cơ chế sandbox. Nó chỉ điều khiển một số hành vi tự tạo object và mở rộng collection. Các quyền khác như gọi method, tham chiếu kiểu, constructor hoặc truy cập bean phụ thuộc vào EvaluationContext và các resolver được cấu hình.

Không nhận một chuỗi SpEL tùy ý từ request rồi đánh giá bằng context có quyền rộng. Nếu người dùng có thể định nghĩa điều kiện, hãy giới hạn grammar, root object, thuộc tính, kiểu dữ liệu, độ dài biểu thức và kích thước collection. Ưu tiên context chỉ đọc, DTO nhỏ và allowlist các trường cần dùng.

Khi bật auto grow:

1. Chỉ cho phép cập nhật trên object có cấu trúc và kiểu đã biết.
2. Đặt giới hạn tăng trưởng phù hợp với dữ liệu nghiệp vụ.
3. Tránh truyền service hoặc entity graph lớn vào root object.
4. Không đăng ký bean resolver, type locator hay method resolver mạnh nếu use case không cần.
5. Kiểm tra kết quả và xử lý exception tại ranh giới ứng dụng.
6. Không ghi dữ liệu nhạy cảm hoặc toàn bộ input không tin cậy vào log.

## 10. Kiểm thử hành vi auto grow

Nên có các test độc lập cho hai cờ và một test tích hợp cho trường hợp kết hợp:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Thuộc tính trung gian null, auto grow null bật | Property path có thể khởi tạo object khi kiểu đích tạo được |
| Thuộc tính trung gian null, auto grow null tắt | Không có object tự sinh; thao tác truy cập thất bại theo ngữ cảnh |
| Index vượt kích thước, auto grow collection bật | Collection tăng đủ để truy cập index trong giới hạn |
| Index vượt giới hạn cấu hình | Đánh giá bị từ chối bằng exception |
| Phần tử tại index mới là null, chỉ bật auto grow collection | Vị trí có thể tồn tại nhưng truy cập thuộc tính phần tử vẫn thất bại |
| Bật cả hai cờ với generic element type cụ thể | Collection được mở rộng và phần tử có thể được khởi tạo để cập nhật thuộc tính |
| Kiểu phần tử không thể tạo instance | Auto grow null reference không thể tạo phần tử phù hợp |
| Đánh giá lặp lại cùng object | Kiểm tra không tạo thêm thay đổi ngoài dự kiến |

Một test nên kiểm tra cả kết quả biểu thức và trạng thái object sau đánh giá. Ví dụ, sau khi gán items[2].sku, hãy xác nhận List có kích thước 3, phần tử tại index 2 tồn tại và giá trị sku đúng. Với test lỗi, hãy xác nhận exception phù hợp và object không bị thay đổi ngoài dự kiến.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đường dẫn vẫn lỗi khi property null | Auto grow null references chưa bật hoặc kiểu đích không thể khởi tạo | Kiểm tra parser configuration, metadata kiểu và constructor |
| Index ngoài phạm vi vẫn lỗi | Auto grow collections chưa bật hoặc vượt giới hạn | Kiểm tra cờ thứ hai và maximum auto grow size |
| List đã tăng nhưng truy cập .property lỗi | Phần tử tại index vẫn null | Cần bật auto grow null references và xác định được kiểu phần tử |
| Không tạo được phần tử generic | Collection khai báo raw hoặc kiểu phần tử không rõ | Khai báo generic cụ thể như List<LineItem> |
| Biểu thức làm thay đổi object ngoài dự kiến | Auto grow phát sinh side effect trong lúc evaluate | Tắt auto grow ở luồng chỉ đọc hoặc dùng object riêng |
| Cấu hình không có tác dụng | Đang dùng parser khác với parser đã cấu hình | Kiểm tra nơi tạo parser và nơi expression được parse |

Khi điều tra, hãy kiểm tra lần lượt parser thực tế, hai cờ cấu hình, index được truy cập, giới hạn kích thước, kiểu property và kiểu phần tử. Đừng chỉ tăng giới hạn hoặc bật thêm quyền nếu chưa xác định được nguyên nhân.

## 12. Lộ trình thực hành

1. Tạo class Person có thuộc tính Address ban đầu null. Dùng parser chỉ bật auto grow null references và gán address.city.
2. Tạo class Order có List<LineItem> rỗng. Chỉ bật auto grow collections và gán một phần tử tại index 2.
3. Kết hợp hai cờ để gán items[2].sku, quan sát object được tạo và kích thước List.
4. Thử tắt từng cờ để hiểu lỗi xuất hiện ở bước nào.
5. Đặt giới hạn nhỏ, thử index nằm trong và vượt giới hạn.
6. Viết test cho property không thể khởi tạo, collection raw type, null và đánh giá lặp lại.
7. Tạo một context chỉ đọc cho use case kiểm tra điều kiện và so sánh với luồng cập nhật có auto-grow.

## 13. Checklist sử dụng trong ứng dụng

- [ ] Đã xác định rõ property path nào cần tự khởi tạo chưa?
- [ ] Đã xác định collection nào được phép tự mở rộng chưa?
- [ ] Hai cờ auto grow đã được bật đúng nhu cầu chưa?
- [ ] Kiểu thuộc tính và generic element type có đủ thông tin không?
- [ ] Các class cần khởi tạo có thể tạo instance trong runtime không?
- [ ] Đã đặt maximum auto grow size phù hợp chưa?
- [ ] Đã xác định side effect lên object graph chưa?
- [ ] Có tránh đánh giá biểu thức không tin cậy bằng context nhiều quyền không?
- [ ] Đã kiểm thử cả kết quả và trạng thái object sau evaluate chưa?
- [ ] Đã xử lý exception và giới hạn nghiệp vụ ở tầng ứng dụng chưa?

## 14. Kết luận

Auto grow null references và auto grow collections giải quyết hai vấn đề riêng: tạo object trung gian đang null và mở rộng collection để đáp ứng index. Khi một biểu thức truy cập sâu như items[2].sku, hai khả năng có thể cần phối hợp. Hãy cấu hình chúng tường minh tại parser, xác định kiểu dữ liệu có thể khởi tạo, đặt giới hạn tăng trưởng và xem mọi lần auto-grow là một thay đổi trạng thái cần được kiểm soát.