# Indexer null-safe ?.[] và các dạng null-safe liên quan

## 1. Vì sao cần null-safe indexing?

Spring Expression Language (SpEL) cho phép truy cập phần tử của array, collection, String, Map và property của object bằng cú pháp indexer. Ví dụ:

    members[0]
    settings['theme']
    customer['name']

Những biểu thức này hoạt động khi object đứng trước dấu ngoặc vuông có thể được truy cập. Nếu object đó là null, việc indexing thông thường có thể phát sinh evaluation error.

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe index operator với cú pháp:

    target?.[index]

Ví dụ:

    members?.[0]

Nếu members là null, biểu thức trả về null thay vì phát sinh NullPointerException. Nếu members tồn tại, SpEL thực hiện indexing như bình thường.

Null-safe indexer đặc biệt hữu ích khi dữ liệu có cấu trúc lồng nhau, collection có thể chưa được khởi tạo hoặc một key có thể tham chiếu đến object không tồn tại.

## 2. Cú pháp và ý nghĩa của ?.[]

Cú pháp tổng quát:

    expression?.[indexExpression]

Trong đó:

- expression là object hoặc cấu trúc cần truy cập.
- ?. là dấu hiệu yêu cầu thao tác indexing an toàn khi receiver null.
- indexExpression là chỉ số hoặc key dùng để lấy phần tử.

Ví dụ với List:

    members?.[0]

Ví dụ với Map:

    settings?.['theme']

Ví dụ với String:

    title?.[0]

Ví dụ với object được truy cập theo tên property:

    customer?.['name']

Khi receiver là null, null-safe indexer trả về null. Khi receiver không null, SpEL tiếp tục xử lý indexer theo kiểu dữ liệu và index được cung cấp.

Cần nhớ dấu ?. nằm trước dấu ngoặc vuông. Cách viết đúng là:

    members?.[0]

Không viết:

    members?[0]

hoặc:

    members[?.0]

Đây là một cú pháp riêng của SpEL, không phải cú pháp indexer thông thường của Java.

## 3. Các cấu trúc được hỗ trợ

SpEL hỗ trợ indexing trên nhiều loại cấu trúc. Indexer có thể truy cập phần tử theo vị trí, key hoặc tên property tùy kiểu dữ liệu.

| Cấu trúc | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Array | colors?.[0] | Phần tử đầu tiên |
| List | members?.[0] | Phần tử đầu tiên |
| Collection có thứ tự truy cập | items?.[2] | Phần tử tại vị trí index |
| String | title?.[0] | Ký tự tại vị trí index, trả về String |
| Map | settings?.['theme'] | Giá trị theo key theme |
| Object | customer?.['name'] | Property name của object |
| Custom structure | payload?.['id'] | Phần tử theo IndexAccessor đã đăng ký |

Index số của array, List và String bắt đầu từ 0, giống quy ước indexing phổ biến trong Java.

Với Map, phần trong ngoặc vuông là key. Kiểu của key cần phù hợp với Map thực tế.

Với object, indexer có thể dùng tên property dưới dạng chuỗi. Khả năng đọc property phụ thuộc vào property accessor mà EvaluationContext cung cấp.

Từ Spring Framework 6.2, ứng dụng cũng có thể đăng ký IndexAccessor để hỗ trợ indexing trên cấu trúc dữ liệu tùy chỉnh. Null-safe indexer có thể được dùng với các cấu trúc mà EvaluationContext có accessor tương ứng.

## 4. Ví dụ với List và root object

Giả sử có một lớp Society chứa danh sách thành viên:

    public class Society {
        private List<Inventor> members;

        public List<Inventor> getMembers() {
            return members;
        }

        public void setMembers(List<Inventor> members) {
            this.members = members;
        }
    }

Có thể dùng SpEL để lấy thành viên đầu tiên:

    ExpressionParser parser = new SpelExpressionParser();

    Society society = new Society();
    society.setMembers(
        List.of(new Inventor("Nikola Tesla"))
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext(society);

    Expression expression =
        parser.parseExpression("members?.[0]");

    Inventor first =
        expression.getValue(context, Inventor.class);

Khi members có dữ liệu, kết quả là phần tử ở vị trí 0.

Nếu danh sách chưa được khởi tạo:

    society.setMembers(null);

    Inventor first =
        expression.getValue(context, Inventor.class);

Kết quả là null. Null-safe indexer ngăn lỗi phát sinh chỉ vì members là null.

Ví dụ này dùng members làm property của root object society. Nếu danh sách được đặt trong variable, có thể viết:

    #members?.[0]

và đưa members vào EvaluationContext bằng setVariable.

## 5. Ví dụ với Map

Indexer của Map sử dụng key để lấy value.

    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "dark");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("settings", settings);

    Expression expression =
        parser.parseExpression("#settings?.['theme']");

    String theme =
        expression.getValue(context, String.class);

Kết quả là:

    dark

Nếu settings là null:

    context.setVariable("settings", null);

thì cùng biểu thức trả về null.

Null-safe indexer chỉ bảo vệ receiver settings khi nó null. Nó không tự thay thế một key không tồn tại bằng giá trị mặc định. Với Map thông thường, key không tồn tại thường trả về null; có thể kết hợp Elvis nếu muốn default:

    #settings?.['theme'] ?: 'light'

Nếu settings null hoặc giá trị theme là null hoặc chuỗi rỗng, biểu thức trên trả về light. Nếu theme là chuỗi có nội dung, giá trị đó được giữ lại.

## 6. Null-safe indexing không bỏ qua index không hợp lệ

Null-safe indexer giải quyết trường hợp receiver là null. Nó không biến mọi lỗi indexing thành null.

Ví dụ:

    members?.[0]

Nếu members là null, kết quả là null.

Nếu members là một List rỗng, receiver không null nhưng không có phần tử ở index 0. Việc indexing vẫn có thể phát sinh lỗi vượt giới hạn.

Tương tự, với array, List hoặc String không rỗng nhưng index vượt giới hạn, null-safe operator không tự xử lý lỗi đó.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Receiver là null | Trả về null |
| Receiver có phần tử tại index | Trả về phần tử |
| List rỗng, truy cập index 0 | Có thể phát sinh lỗi index ngoài phạm vi |
| Index âm hoặc vượt giới hạn | Có thể phát sinh lỗi index ngoài phạm vi |
| Map không có key | Thường trả về null theo hành vi của Map |
| Phần tử được lấy ra là null | Kết quả indexer là null; bước truy cập tiếp theo cần được bảo vệ riêng |

Nếu cần kiểm tra cả null và collection rỗng, hãy dùng điều kiện tường minh:

    #members != null and !#members.isEmpty()
        ? #members[0]
        : null

Vế kiểm tra null đứng trước. Nhờ short-circuit của AND, SpEL không gọi isEmpty() khi members là null.

Với array, String, Map hoặc custom structure, hãy viết điều kiện phù hợp với kiểu dữ liệu tương ứng.

## 7. Kết hợp với property navigation

Null-safe indexing thường chỉ là một bước trong đường dẫn truy cập object.

Ví dụ:

    members?.[0].name

Biểu thức này bảo vệ thao tác indexing khi members là null. Tuy nhiên, nếu phần tử đầu tiên là null, bước truy cập .name phía sau vẫn có thể thất bại.

Cách viết an toàn hơn:

    members?.[0]?.name

Trong biểu thức này:

1. Nếu members là null, null-safe indexer trả về null.
2. Nếu phần tử đầu tiên là null, null-safe property navigation trả về null.
3. Nếu cả hai đều tồn tại, SpEL đọc property name.

Ví dụ với nhiều tầng:

    #society?.members?.[0]?.placeOfBirth?.city

Mỗi ?. bảo vệ receiver của thao tác ngay sau nó. Cách viết này phù hợp khi bất kỳ object trung gian nào cũng có thể null.

Không nên nghĩ rằng một toán tử null-safe ở đầu chuỗi sẽ tự động làm toàn bộ phần còn lại an toàn.

## 8. Quy tắc quan trọng với compound expression

Trong SpEL, khi một thao tác null-safe trả về null bên trong compound expression, phần còn lại của compound expression vẫn tiếp tục được đánh giá.

Ví dụ:

    #person?.address.city

Nếu person là null, thao tác truy cập address trả về null. Sau đó SpEL vẫn tiếp tục với .city. Vì receiver của .city là null và bước này không null-safe, expression có thể phát sinh NullPointerException.

Cách viết an toàn:

    #person?.address?.city

Quy tắc tương tự áp dụng cho indexer:

    #person?.orders?.[0]?.items?.[0]?.name

Mỗi bước có thể nhận receiver null đều cần được bảo vệ riêng nếu mục tiêu là để toàn bộ expression trả về null thay vì phát sinh lỗi.

Đây là điểm quan trọng nhất khi ghép null-safe indexer với property access, method invocation hoặc indexer khác.

## 9. Null-safe selection và projection

Ngoài indexer, SpEL còn có các toán tử null-safe dành cho collection selection và projection.

Các dạng thường dùng:

| Thao tác | Cú pháp thường | Cú pháp null-safe |
| --- | --- | --- |
| Selection tất cả phần tử phù hợp | members.?[condition] | members?.?[condition] |
| Chọn phần tử phù hợp đầu tiên | members.^[condition] | members?.^[condition] |
| Chọn phần tử phù hợp cuối cùng | members.$[condition] | members?.$[condition] |
| Projection | members.![expression] | members?.![expression] |

Các toán tử null-safe này cho phép thực hiện selection hoặc projection khi collection có thể null.

### Null-safe selection

Selection lọc các phần tử thỏa điều kiện:

    members?.?[nationality == 'Serbian']

Nếu members là null, kết quả là null. Nếu members tồn tại, SpEL lọc các phần tử phù hợp và trả về collection kết quả.

Ví dụ với variable:

    List<Inventor> serbians =
        parser.parseExpression(
            "#members?.?[nationality == 'Serbian']"
        ).getValue(context, List.class);

### Null-safe select first và select last

Để lấy phần tử đầu tiên thỏa điều kiện:

    members?.^[nationality == 'Serbian']

Để lấy phần tử cuối cùng thỏa điều kiện:

    members?.$[nationality == 'Serbian']

Nếu source collection là null, hai biểu thức null-safe trả về null. Nếu collection tồn tại nhưng không có phần tử thỏa điều kiện, kết quả chọn phần tử cũng có thể là null.

### Null-safe projection

Projection biến đổi mỗi phần tử thành một giá trị hoặc property:

    members?.![placeOfBirth.city]

Nếu members là null, kết quả là null. Nếu collection tồn tại, SpEL áp dụng expression projection lên từng phần tử và trả về collection kết quả.

Null-safe projection chỉ bảo vệ collection nguồn. Nếu placeOfBirth của một phần tử có thể null, cần tiếp tục dùng null-safe navigation bên trong projection:

    members?.![placeOfBirth?.city]

Điều này tránh nhầm lẫn giữa việc collection nguồn null và việc một property bên trong từng phần tử null.

## 10. Null source khác collection rỗng

Null-safe operator không chuyển một collection null thành collection rỗng.

Ví dụ:

    #members?.?[active == true]

Nếu members là null, kết quả là null.

Nếu members là một collection rỗng, selection chạy trên collection rỗng và trả về collection rỗng.

Tương tự, projection trên collection rỗng trả về collection kết quả rỗng. Select first hoặc select last trên collection không có phần tử phù hợp trả về null.

Phân biệt này quan trọng khi code phía sau cần kiểm tra kích thước collection:

- null biểu thị không có source collection.
- collection rỗng biểu thị source tồn tại nhưng không có phần tử.
- null-safe selection/projection giữ sự khác biệt đó.

Nếu nghiệp vụ muốn biến null thành collection rỗng, có thể dùng Elvis với collection rỗng được tạo phù hợp hoặc chuẩn hóa dữ liệu trước khi đánh giá.

## 11. Phiên bản Spring Framework

Null-safe indexing được hỗ trợ từ Spring Framework 6.2.

Cú pháp:

    members?.[0]

Không nên giả định biểu thức này chạy được trên các phiên bản Spring Framework cũ hơn. Nếu ứng dụng đang dùng phiên bản trước 6.2, hãy kiểm tra version thực tế trước khi sử dụng.

Với phiên bản chưa hỗ trợ null-safe indexer, có thể dùng điều kiện ternary để kiểm tra receiver trước:

    #members != null and !#members.isEmpty()
        ? #members[0]
        : null

Cách thay thế phải phù hợp với loại cấu trúc và yêu cầu kiểm tra index. Chỉ kiểm tra null là chưa đủ nếu collection có thể rỗng.

Các dạng null-safe selection và projection cũng được mô tả trong tài liệu SpEL hiện hành. Hãy đối chiếu tài liệu theo đúng phiên bản Spring Framework mà ứng dụng đang chạy.

## 12. Lỗi thường gặp và cách debug

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Parse error tại ?.[] | Spring Framework chưa hỗ trợ cú pháp hoặc expression viết sai | Kiểm tra version và cú pháp target?.[index] |
| NullPointerException sau indexer | Bước property/method tiếp theo không null-safe | Dùng ?. ở từng receiver có thể null |
| Index out of bounds | Receiver tồn tại nhưng index không hợp lệ | Kiểm tra kích thước hoặc giới hạn index |
| Kết quả null ngoài dự kiến | Receiver null, key không tồn tại hoặc phần tử được lấy ra null | Kiểm tra từng bước trong đường dẫn |
| Selection trả null thay vì collection rỗng | Collection nguồn là null | Chuẩn hóa null thành collection rỗng nếu nghiệp vụ yêu cầu |
| Projection thất bại | Property bên trong một phần tử null | Dùng null-safe navigation trong projection expression |
| Custom structure không indexing được | Chưa có IndexAccessor phù hợp | Đăng ký accessor trong EvaluationContext |

Khi debug, hãy tách biểu thức thành từng bước:

    #members
    #members?.[0]
    #members?.[0]?.name

Đánh giá từng bước giúp xác định receiver nào null, index có hợp lệ không và property nào gây lỗi.

Đừng chỉ nhìn vào kết quả cuối cùng. Một expression có thể trả null vì receiver null, key không tồn tại hoặc phần tử null; các trường hợp đó có ý nghĩa nghiệp vụ khác nhau.

## 13. Những điểm cần nhớ

- Null-safe indexer có cú pháp target?.[index].
- Tính năng indexing null-safe được hỗ trợ từ Spring Framework 6.2.
- Indexer có thể truy cập array, collection, String, Map, object và custom structure có IndexAccessor phù hợp.
- Index số bắt đầu từ 0.
- Receiver null trả về null; receiver tồn tại nhưng index không hợp lệ vẫn có thể phát sinh lỗi.
- Null-safe indexer không tự bảo vệ property hoặc method được truy cập sau đó.
- Dùng ?. tại từng bước có thể nhận receiver null trong compound expression.
- Null-safe selection, select first, select last và projection dùng lần lượt ?.?, ?.^, ?.$ và ?.!.
- Collection null khác collection rỗng; null-safe operator không tự chuyển null thành collection rỗng.
- Khi debug, kiểm tra version, receiver, index, phần tử được lấy ra và từng bước truy cập tiếp theo.

Hãy dùng null-safe indexer để xử lý trường hợp cấu trúc nguồn có thể null, nhưng vẫn kiểm tra index và dữ liệu bên trong theo quy tắc nghiệp vụ. Null-safe navigation giúp tránh lỗi truy cập null ở đúng thao tác được đánh dấu; nó không thay thế validation cho toàn bộ object graph.

## Tài liệu tham khảo

- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Javadoc — Indexer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Indexer.html
