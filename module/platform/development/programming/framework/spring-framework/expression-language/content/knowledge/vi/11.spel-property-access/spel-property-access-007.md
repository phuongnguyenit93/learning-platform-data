# Null-safe navigation bằng toán tử ?. trong SpEL

Trong Spring Expression Language (SpEL), toán tử null-safe navigation ?. cho phép truy cập property hoặc gọi method khi đối tượng nhận có thể là null. Nếu receiver của thao tác là null, SpEL trả về null cho thao tác đó thay vì phát sinh NullPointerException ngay tại vị trí truy cập.

Toán tử này hữu ích khi làm việc với object graph có nhiều tầng, dữ liệu request không đầy đủ, kết quả truy vấn có thể vắng mặt hoặc thuộc tính tùy chọn. Tuy nhiên, ?. chỉ bảo vệ thao tác mà nó đứng trước. Trong một biểu thức ghép, các bước tiếp theo vẫn được đánh giá; vì vậy cần đặt toán tử null-safe ở từng mắt xích có thể null.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt truy cập property thông thường bằng dấu chấm và null-safe navigation bằng ?.
- Dùng null-safe operator cho property và method.
- Bảo vệ từng tầng trong một property path lồng nhau.
- Kết hợp null-safe navigation với Elvis, so sánh và biểu thức điều kiện.
- Nhận biết các dạng null-safe indexing, selection và projection trong Spring Framework 6.2 trở lên.
- Phân biệt đối tượng null với collection rỗng, index không hợp lệ và exception từ method.
- Kiểm thử hành vi null và lựa chọn cách xử lý mặc định phù hợp với nghiệp vụ.

Bạn nên biết Java object, getter, method, collection, biến SpEL có tiền tố # và cách đánh giá Expression bằng EvaluationContext.

## 2. Vấn đề khi truy cập object có thể null

Giả sử có các lớp:

~~~java
class Person {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

Nếu person tồn tại và address cũng tồn tại, biểu thức truy cập city có thể hoạt động:

~~~text
#person.address.city
~~~

Nhưng nếu person hoặc address là null, một thao tác truy cập property thông thường có thể phát sinh lỗi khi đánh giá. Đây là tình huống phổ biến khi dữ liệu đến từ form, API, database hoặc một object graph có nhiều thuộc tính tùy chọn.

Có thể xử lý bằng các điều kiện kiểm tra null, nhưng biểu thức sẽ dài khi đường dẫn có nhiều tầng. Null-safe navigation cung cấp cách viết ngắn hơn và thể hiện trực tiếp rằng một nhánh có thể không tồn tại.

## 3. Cú pháp cơ bản của ?. 

Dấu chấm thông thường:

~~~text
#person.address
~~~

Null-safe navigation:

~~~text
#person?.address
~~~

Nếu person là null, biểu thức thứ hai trả về null cho thao tác truy cập address. Nếu person tồn tại, SpEL đọc property address như bình thường.

Có thể dùng với method:

~~~text
#person?.getAddress()
~~~

Nếu person là null, method getAddress() không được gọi và thao tác trả về null. Nếu person tồn tại, method được gọi theo cơ chế method resolver của EvaluationContext.

Ví dụ trong Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#person?.name");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("person", null);

Object result = expression.getValue(context);
~~~

Kết quả là null. Nếu thay person bằng một object có property name, biểu thức trả về giá trị của property đó.

Null-safe navigation không tạo object thay thế và cũng không tự gán một giá trị mặc định. Nó chỉ làm cho thao tác trên receiver null trả về null.

## 4. Bảo vệ từng tầng của property path

Một điểm rất quan trọng là ?. không tự động biến toàn bộ phần còn lại của một compound expression thành null-safe.

Ví dụ:

~~~text
#person?.address.city
~~~

Toán tử ?. bảo vệ việc đọc address trên person. Nếu person null, thao tác đó trả về null; phần .city phía sau vẫn là một bước trong biểu thức ghép và vẫn có thể được đánh giá trên kết quả null.

Vì vậy, khi cả person và address đều có thể null, hãy viết:

~~~text
#person?.address?.city
~~~

Cách đọc:

1. Nếu person null, kết quả của bước đầu là null.
2. Nếu person tồn tại, đọc address.
3. Nếu address null, bước thứ hai trả về null.
4. Nếu address tồn tại, đọc city.

Có thể áp dụng cùng nguyên tắc cho nhiều tầng:

~~~text
#order?.customer?.profile?.displayName
~~~

Mỗi dấu ?. bảo vệ receiver của thao tác tiếp theo. Hãy đặt nó tại mọi ranh giới mà dữ liệu có thể null, thay vì chỉ đặt một lần ở đầu đường dẫn.

### 4.1. So sánh với kiểm tra null tường minh

Cách viết tường minh:

~~~text
#person != null and
#person.address != null and
#person.address.city != null
~~~

Cách viết bằng safe navigation:

~~~text
#person?.address?.city != null
~~~

Cách thứ hai ngắn hơn và tập trung vào property path. Tuy nhiên, nếu nghiệp vụ cần phân biệt person không tồn tại, address không tồn tại và city không tồn tại, các điều kiện tường minh có thể dễ biểu đạt hơn.

Không nên rút gọn một biểu thức chỉ để giảm số ký tự nếu điều đó làm mất ý nghĩa nghiệp vụ của từng trạng thái null.

## 5. Null-safe navigation với method

Có thể gọi method trên một đối tượng có khả năng null:

~~~text
#customer?.getDisplayName()
~~~

Nếu customer null, method không được gọi và kết quả là null. Nếu customer tồn tại, SpEL gọi method và nhận kết quả trả về.

Nếu method tồn tại nhưng bản thân nó trả về null, một thao tác tiếp theo vẫn cần được bảo vệ:

~~~text
#customer?.getProfile()?.getDisplayName()
~~~

Ở đây có hai tình huống khác nhau:

- customer null: getProfile() không được gọi.
- customer tồn tại nhưng getProfile() trả về null: thao tác getDisplayName() được bảo vệ bởi ?. thứ hai.

Toán tử không bắt hoặc che giấu exception do method ném ra. Nếu method được gọi và ném exception, lỗi vẫn có thể xuất hiện trong quá trình evaluate. Null-safe navigation cũng không kiểm tra method có tác dụng phụ hay không; hãy ưu tiên method chỉ đọc và có kết quả dễ dự đoán.

## 6. Kết hợp với Elvis để cung cấp giá trị mặc định

Null-safe navigation thường trả về null khi receiver null. Nếu ứng dụng cần một giá trị thay thế, có thể kết hợp với Elvis operator ?:.

Ví dụ:

~~~text
#person?.name ?: 'Anonymous'
~~~

Nếu person null hoặc name null, kết quả là Anonymous. Nếu name có giá trị khác null, kết quả là tên đó.

Một property path nhiều tầng:

~~~text
#order?.customer?.profile?.displayName ?: 'Guest'
~~~

Elvis giúp xử lý trường hợp null ở cuối biểu thức và cung cấp giá trị mặc định ngắn gọn.

Cần chọn default đúng với ý nghĩa nghiệp vụ. Ví dụ thay null bằng 0 có thể khiến dữ liệu chưa được xác định bị hiểu nhầm thành giá trị bằng 0. Với dữ liệu quan trọng, có thể cần báo lỗi validation thay vì tự thay thế.

### 6.1. Phân biệt ?. và ?:

Hai toán tử có mục đích khác nhau:

| Toán tử | Vai trò |
|---|---|
| ?. | Bảo vệ một thao tác truy cập property hoặc method khi receiver là null |
| ?: | Chọn giá trị thay thế khi biểu thức bên trái là null |

Có thể kết hợp chúng:

~~~text
#customer?.address?.city ?: 'Unknown'
~~~

Dấu ?. xử lý các receiver null trong đường dẫn; Elvis cung cấp giá trị mặc định nếu kết quả cuối cùng là null.

## 7. Kết hợp với so sánh và toán tử logic

Kết quả null-safe có thể được dùng trong điều kiện. Ví dụ:

~~~text
#customer?.status == 'ACTIVE'
~~~

Nếu customer null, biểu thức property trả về null và phép so sánh với chuỗi ACTIVE không thành true. Tuy nhiên, nếu cần phân biệt rõ null với một trạng thái không hợp lệ, hãy kiểm tra tường minh.

Ví dụ kiểm tra trạng thái và quyền:

~~~text
#customer?.status == 'ACTIVE' and #user?.enabled == true
~~~

Cả hai vế đều phải đúng. Có thể dùng Elvis để cung cấp giá trị boolean mặc định:

~~~text
(#user?.enabled ?: false) and (#customer?.verified ?: false)
~~~

Cách viết này coi null như false. Chỉ dùng khi đó là quy tắc nghiệp vụ mong muốn.

### 7.1. Kết hợp với short-circuit

AND và OR có thể dừng đánh giá khi kết quả đã xác định. Có thể dùng guard ở vế trái:

~~~text
#person != null and #person.address?.city == 'Hanoi'
~~~

Nếu person null, vế phải được bỏ qua. Nếu person tồn tại, address?.city bảo vệ trường hợp address null.

Khi dùng safe navigation, không cần thêm guard cho cùng receiver nếu toán tử đã bảo vệ đúng thao tác. Tuy nhiên, hãy giữ điều kiện tường minh nếu nó còn mang ý nghĩa nghiệp vụ khác ngoài null safety.

## 8. Null-safe indexing, selection và projection

Spring Framework 6.2 bổ sung các dạng null-safe cho thao tác collection và index. Các cú pháp này cần được dùng đúng phiên bản; nếu dự án đang chạy Spring Framework trước 6.2, parser có thể không hỗ trợ chúng.

### 8.1. Null-safe indexing

Cú pháp:

~~~text
#members?.[0]
~~~

Nếu members null, kết quả là null thay vì cố truy cập index. Nếu members tồn tại, SpEL thực hiện truy cập index 0 như bình thường.

Có thể kết hợp với null-safe navigation trên phần tử:

~~~text
#members?.[0]?.name
~~~

Ở đây có hai ranh giới null riêng:

- Collection members có thể null.
- Phần tử tại index 0 có thể null.

Null-safe indexing chỉ bảo vệ collection receiver. Nó không biến một index ngoài phạm vi thành index hợp lệ; nếu collection tồn tại nhưng rỗng, truy cập index 0 vẫn có thể thất bại. Nếu cần xử lý collection rỗng, hãy kiểm tra size hoặc dùng logic phù hợp trước khi lấy phần tử.

Với Map, có thể dùng null-safe index để bảo vệ map receiver khi truy cập key:

~~~text
#settings?.['theme']
~~~

Key không tồn tại và map null là hai tình huống khác nhau. Cách xử lý key vắng mặt phụ thuộc vào Map/accessor và chính sách default của ứng dụng.

### 8.2. Null-safe selection

Selection lọc các phần tử thỏa điều kiện. Dạng null-safe trong Spring Framework 6.2 trở lên:

~~~text
#members?.?[active == true]
~~~

Nếu members null, thao tác selection trả về null. Nếu collection tồn tại, SpEL lọc các phần tử theo predicate.

Có thể kết hợp với Elvis nếu muốn collection kết quả mặc định là collection rỗng, nhưng cần chọn kiểu và giá trị default phù hợp. Không nên mặc định null collection đồng nghĩa collection rỗng nếu hai trạng thái mang ý nghĩa khác nhau.

### 8.3. Null-safe projection

Projection tạo một collection kết quả bằng cách áp dụng biểu thức cho từng phần tử. Dạng null-safe:

~~~text
#members?.![displayName]
~~~

Nếu members null, thao tác projection trả về null. Nếu collection tồn tại, SpEL tạo kết quả từ displayName của từng phần tử.

Nếu phần tử bên trong collection có thể null, hãy bảo vệ property của phần tử trong projection khi cần:

~~~text
#members?.![#this?.displayName]
~~~

Null-safe projection bảo vệ collection receiver; safe navigation bên trong biểu thức projection bảo vệ phần tử hiện tại.

## 9. Phân biệt null với collection rỗng và index không hợp lệ

Null-safe navigation không phải là cơ chế xử lý mọi trường hợp không có dữ liệu.

| Tình huống | Ý nghĩa | Cách xử lý |
|---|---|---|
| Receiver là null | Không có object để thực hiện thao tác | Dùng ?. hoặc kiểm tra null |
| Collection rỗng | Collection tồn tại nhưng không có phần tử | Kiểm tra size/isEmpty trước khi truy cập index |
| Index ngoài phạm vi | Collection có phần tử nhưng index yêu cầu không hợp lệ | Kiểm tra kích thước hoặc dùng luồng xử lý phù hợp |
| Map thiếu key | Map tồn tại nhưng không có entry cho key đó | Kiểm tra containsKey hoặc dùng default rõ ràng |
| Method ném exception | Method đã được gọi nhưng thực thi thất bại | Xử lý exception theo hợp đồng method |
| Property không tồn tại | Cấu trúc object hoặc tên property không đúng | Kiểm tra model và accessor |

Ví dụ, biểu thức:

~~~text
#items?.[0]
~~~

bảo vệ trường hợp items null. Nó không bảo vệ trường hợp items là List rỗng. Để lấy phần tử đầu tiên an toàn, cần kiểm tra collection có phần tử trước khi đọc index.

## 10. Null-safe navigation không phải auto grow

Hai cơ chế này có mục đích ngược nhau:

- Null-safe navigation trả về null khi receiver null, cho phép biểu thức tiếp tục theo quy tắc đánh giá.
- Auto grow null references có thể tạo object trung gian khi parser được cấu hình phù hợp và kiểu object có thể khởi tạo.

Ví dụ safe navigation:

~~~text
#person?.address?.city
~~~

Nếu person null, biểu thức không tạo Person hay Address mới.

Auto grow là cấu hình parser riêng:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, false);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Nếu use case cần cập nhật object graph, hãy xem xét auto grow và điều kiện ghi property. Nếu chỉ cần đọc dữ liệu tùy chọn, safe navigation thường phù hợp hơn. Không dùng null-safe operator với kỳ vọng nó sẽ tự tạo object để có thể ghi.

## 11. Đánh giá bằng Java và EvaluationContext

Ví dụ đầy đủ với biến:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#person?.address?.city ?: 'Unknown'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("person", null);

String city = expression.getValue(context, String.class);
~~~

Kết quả là Unknown.

Nếu person có address và city, biểu thức trả về tên thành phố. Nếu person tồn tại nhưng address null, biểu thức cũng trả về Unknown vì từng tầng đều được bảo vệ.

Khi truyền dữ liệu từ request hoặc người dùng, hãy truyền qua biến hoặc root object có kiểu rõ ràng. Tránh nối input vào chuỗi SpEL để tạo property path hoặc cú pháp tùy ý.

## 12. Kiểm thử và debug

Hãy kiểm thử ít nhất các trường hợp:

| Trường hợp | Dữ liệu | Kết quả cần xác nhận |
|---|---|---|
| Receiver tồn tại | person có name | Trả về name |
| Receiver null | person = null | Null-safe property trả về null |
| Tầng giữa null | person tồn tại, address = null | address?.city trả về null |
| Giá trị cuối null | address tồn tại, city = null | Kết quả là null |
| Elvis default | person = null | Trả về giá trị mặc định |
| Method receiver null | service/object = null | Method không được gọi |
| Collection null | members = null | Null-safe index/selection/projection trả về null trên phiên bản hỗ trợ |
| Collection rỗng | members = [] | Index 0 vẫn không hợp lệ; cần xử lý riêng |
| Phần tử null | members có null ở index 0 | Cần null-safe navigation trên phần tử |
| Method ném exception | receiver tồn tại | Exception vẫn được truyền ra theo hành vi evaluate |

Khi debug, hãy tách biểu thức thành từng bước:

1. Xác nhận biến hoặc root object có tồn tại không.
2. Kiểm tra từng property path và vị trí có thể null.
3. Thêm ?. đúng tại receiver có thể null.
4. Kiểm tra collection rỗng và index riêng biệt.
5. Thêm Elvis hoặc điều kiện mặc định nếu nghiệp vụ yêu cầu.
6. Kiểm tra lại kết quả với object đầy đủ, object null và object thiếu từng tầng.

Nếu cú pháp null-safe indexing/selection/projection không parse được, kiểm tra phiên bản Spring Framework đang chạy trước khi thay đổi biểu thức.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Vẫn gặp lỗi ở property phía sau | Chỉ có ?. ở tầng đầu, tầng sau vẫn có thể null | Dùng ?. tại từng mắt xích nullable |
| Kết quả null thay vì chuỗi mặc định | Chưa dùng Elvis hoặc default logic | Kết hợp ?: khi phù hợp |
| Index vẫn lỗi dù dùng null-safe index | Collection tồn tại nhưng rỗng hoặc index ngoài phạm vi | Kiểm tra size trước khi truy cập |
| Property của phần tử vẫn lỗi | Collection có phần tử null | Dùng safe navigation trên #this hoặc phần tử |
| Method vẫn phát sinh exception | Method đã được gọi và tự ném exception | Xử lý exception theo hợp đồng method |
| Parser không nhận cú pháp ?.[] hoặc ?.?[...] | Dùng Spring Framework trước 6.2 | Kiểm tra dependency version hoặc dùng guard tương thích |
| Object không được tạo khi receiver null | Safe navigation chỉ trả null, không auto grow | Dùng parser configuration auto grow cho use case ghi phù hợp |

## 14. Bài tập thực hành

1. Tạo Person có Address và City; đánh giá #person?.address?.city khi person lần lượt tồn tại, null và có address null.
2. Viết biểu thức trả về Anonymous nếu name null bằng Elvis.
3. Gọi method qua null-safe navigation và kiểm tra method không chạy khi receiver null.
4. So sánh #person?.address.city với #person?.address?.city khi person null và address null.
5. Trên Spring Framework 6.2+, thử null-safe indexing với List null và List rỗng.
6. Thử null-safe selection và projection; phân biệt collection null với collection rỗng.
7. Tạo collection có phần tử null và bảo vệ property của phần tử trong projection.
8. So sánh safe navigation với auto grow null references trong một use case đọc và một use case cập nhật.

## 15. Checklist trước khi dùng trong ứng dụng

- [ ] Đã xác định receiver nào có thể null chưa?
- [ ] Đã đặt ?. tại từng tầng nullable trong compound expression chưa?
- [ ] Đã phân biệt null với collection rỗng và index ngoài phạm vi chưa?
- [ ] Đã bảo vệ phần tử collection nếu phần tử có thể null chưa?
- [ ] Đã chọn default bằng Elvis theo đúng nghiệp vụ chưa?
- [ ] Đã hiểu method vẫn có thể ném exception khi receiver tồn tại chưa?
- [ ] Đã kiểm tra phiên bản Spring nếu dùng null-safe indexing/selection/projection chưa?
- [ ] Đã phân biệt safe navigation với auto grow chưa?
- [ ] Đã kiểm thử các tầng null và dữ liệu biên chưa?
- [ ] Đã truyền dữ liệu qua context có kiểu rõ ràng chưa?

## 16. Kết luận

Toán tử ?. giúp SpEL truy cập property hoặc gọi method an toàn khi receiver có thể null. Trong biểu thức ghép, hãy bảo vệ từng tầng nullable vì các bước tiếp theo vẫn được đánh giá. Elvis ?: có thể cung cấp giá trị mặc định, còn null-safe indexing, selection và projection cần Spring Framework 6.2 trở lên. Luôn phân biệt object null với collection rỗng, index không hợp lệ và exception từ method. Dùng safe navigation cho luồng đọc dữ liệu tùy chọn; nếu cần tạo object để cập nhật, hãy xem xét cơ chế auto grow riêng.