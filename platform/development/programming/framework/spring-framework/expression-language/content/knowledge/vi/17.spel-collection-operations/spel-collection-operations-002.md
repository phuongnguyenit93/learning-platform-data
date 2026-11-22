# Truy cập size, empty và các thuộc tính collection

## 1. Vì sao cần đọc kích thước và trạng thái collection?

Trong SpEL, biểu thức thường cần biết một collection có bao nhiêu phần tử hoặc có đang rỗng hay không trước khi xử lý tiếp.

Ví dụ:

    members.size()
    members.isEmpty()

Hai biểu thức này gọi các method quen thuộc của Java Collection. SpEL cho phép truy cập property và gọi method trên object, nên có thể sử dụng các API đó ngay trong expression.

Cần phân biệt ba khái niệm:

- **Kích thước (size):** số phần tử hiện có trong Collection hoặc số entry trong Map.
- **Trạng thái rỗng (empty):** collection hoặc map có số phần tử bằng 0 hay không.
- **Thuộc tính của object:** giá trị được truy cập theo quy tắc property accessor, thường thông qua getter hoặc field.

Một số cú pháp trông giống nhau nhưng được SpEL xử lý khác nhau. Đặc biệt, với List hoặc Map thông thường, size() là method; không nên viết size như một property nếu class không có getter tương ứng.

## 2. Đọc size của List, Set và Collection

Các interface Java Collection cung cấp method size() trả về số phần tử hiện có.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable(
        "members",
        List.of("Lan", "Minh", "An")
    );

    Integer count = parser
        .parseExpression("#members.size()")
        .getValue(context, Integer.class);

    // count = 3

Biểu thức #members.size() thực hiện các bước:

1. Tìm variable members trong EvaluationContext.
2. Gọi method size() trên object List.
3. Trả về số phần tử dưới dạng Integer.

Cùng cách viết này áp dụng cho Set hoặc các implementation khác của Collection:

    #members.size()
    #tags.size()
    #permissions.size()

Kết quả là số phần tử hiện có tại thời điểm expression được đánh giá.

Không nên nhầm số phần tử với index cuối cùng. Một List có size bằng 3 có các index hợp lệ là 0, 1 và 2; index cuối cùng thường là size() - 1.

## 3. Đọc size của Map

Map cũng cung cấp method size(). Giá trị trả về là số entry key-value, không phải tổng số key và value cộng lại.

Ví dụ:

    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "dark");
    settings.put("language", "vi");

    context.setVariable("settings", settings);

    Integer count = parser
        .parseExpression("#settings.size()")
        .getValue(context, Integer.class);

    // count = 2

Nếu Map có hai cặp key-value, size() trả về 2.

Cần phân biệt việc gọi method size() với việc đọc một entry có key là size:

    #settings.size()

Gọi method size() để đếm số entry.

    #settings['size']

Đọc value được lưu dưới key chuỗi size.

Khi truy cập Map entry, dùng indexer với key trong ngoặc vuông để thể hiện rõ ý định. Không dùng dấu chấm để thay thế cho key lookup nếu chưa có accessor được thiết kế riêng cho mục đích đó.

## 4. Kiểm tra collection rỗng bằng isEmpty()

Collection và Map cung cấp method isEmpty() để kiểm tra có phần tử hay không.

Ví dụ:

    context.setVariable("members", List.of());

    Boolean empty = parser
        .parseExpression("#members.isEmpty()")
        .getValue(context, Boolean.class);

    // empty = true

Nếu collection có ít nhất một phần tử, isEmpty() trả về false.

Ví dụ:

    context.setVariable("members", List.of("Lan"));

    Boolean empty = parser
        .parseExpression("#members.isEmpty()")
        .getValue(context, Boolean.class);

    // empty = false

isEmpty() trả về boolean, vì vậy có thể sử dụng trực tiếp trong điều kiện:

    #members.isEmpty() ? 'No members' : 'Has members'

Hoặc kết hợp với toán tử logic:

    #members != null and !#members.isEmpty()

Điều kiện null được kiểm tra trước. Nhờ short-circuit của AND, SpEL không gọi isEmpty() nếu members là null.

## 5. Property empty và method isEmpty() khác nhau thế nào?

SpEL hỗ trợ truy cập property thông qua các getter theo quy ước JavaBean.

Với một method boolean có tên isEmpty(), property tương ứng có tên empty. Vì vậy, khi dùng reflective property access mặc định, có thể viết:

    #members.empty

Biểu thức này đọc property empty thông qua getter isEmpty().

Cách gọi method tường minh là:

    #members.isEmpty()

Hai cách trên có thể cho cùng kết quả với Collection chuẩn trong StandardEvaluationContext:

| Cú pháp | Cách SpEL xử lý |
| --- | --- |
| #members.isEmpty() | Gọi trực tiếp method isEmpty() |
| #members.empty | Đọc property empty qua getter isEmpty() |
| #members.size() | Gọi method size() |
| #members.size | Thử đọc property size qua getter getSize(); List chuẩn không có getter này |

Điểm cuối rất dễ gây lỗi. List và Map chuẩn có method size(), nhưng không có JavaBean getter getSize(). Do đó, biểu thức #members.size thường không hoạt động như mong đợi.

Hãy dùng #members.size() để lấy kích thước.

Property empty phụ thuộc vào property accessor được đăng ký trong EvaluationContext. Nếu ứng dụng thay đổi accessor hoặc dùng một context giới hạn, hãy xác nhận accessor đó hỗ trợ đọc getter tương ứng. Khi muốn thể hiện rõ ý định và tránh nhầm với property tùy chỉnh, gọi isEmpty() trực tiếp thường dễ hiểu hơn.

## 6. Array dùng length, không dùng size()

Array trong Java không triển khai Collection và không có method size() hoặc isEmpty().

SpEL hỗ trợ property đặc biệt length cho array:

    int[] scores = {80, 90, 75};

    context.setVariable("scores", scores);

    Integer count = parser
        .parseExpression("#scores.length")
        .getValue(context, Integer.class);

    // count = 3

Kiểm tra array rỗng:

    #scores.length == 0

Không viết:

    #scores.size()
    #scores.isEmpty()

vì array không có các method đó.

So sánh nhanh:

| Loại dữ liệu | Lấy số phần tử | Kiểm tra rỗng |
| --- | --- | --- |
| List | list.size() | list.isEmpty() hoặc list.empty |
| Set | set.size() | set.isEmpty() hoặc set.empty |
| Collection | collection.size() | collection.isEmpty() hoặc collection.empty |
| Map | map.size() | map.isEmpty() hoặc map.empty |
| Array | array.length | array.length == 0 |
| String | string.length() | string.isEmpty() hoặc string.empty |

Với array, length là property đặc biệt do reflective property accessor của SpEL hỗ trợ. Đây không phải method length() của array.

## 7. String cũng có length và isEmpty

String không phải Collection, nhưng có các method hữu ích để kiểm tra nội dung:

    #name.length()
    #name.isEmpty()

Ví dụ:

    context.setVariable("name", "Spring");

    Integer length = parser
        .parseExpression("#name.length()")
        .getValue(context, Integer.class);

    // length = 6

Kiểm tra chuỗi rỗng:

    #name.isEmpty()

Property empty cũng có thể được đọc thông qua getter isEmpty() nếu property accessor cho phép:

    #name.empty

Cần phân biệt chuỗi rỗng với chuỗi chỉ chứa khoảng trắng:

    ''.isEmpty()       // true
    '   '.isEmpty()    // false

Nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là không có nội dung, hãy dùng trim() hoặc isBlank() với phiên bản Java phù hợp:

    #name == null or #name.isBlank()

Không dùng size() cho String. String có length(), không có size().

## 8. Thuộc tính của collection và thuộc tính của phần tử

Một collection có thể chứa các object có property riêng. Cần phân biệt property của collection với property của từng phần tử.

Ví dụ:

    members.size()

Lấy số phần tử của collection members.

    members[0].name

Lấy property name của phần tử đầu tiên.

    members.?[active == true].size()

Lọc thành viên active, sau đó lấy số phần tử trong kết quả selection.

Trong selection, property active được đánh giá trên từng phần tử. Sau khi selection trả về collection kết quả, size() được gọi trên collection đó.

Ví dụ đầy đủ:

    List<Member> members = List.of(
        new Member("Lan", true),
        new Member("Minh", false),
        new Member("An", true)
    );

    context.setVariable("members", members);

    Integer activeCount = parser
        .parseExpression(
            "#members.?[active == true].size()"
        )
        .getValue(context, Integer.class);

    // activeCount = 2

Cách viết này dễ đọc, nhưng selection tạo collection kết quả trước khi gọi size(). Nếu chỉ cần đếm trên collection rất lớn, hãy cân nhắc xử lý ở Java hoặc tầng truy vấn để tránh tạo collection trung gian không cần thiết.

## 9. Truy cập thuộc tính trên object bao bọc collection

Nhiều ứng dụng không truyền trực tiếp List hoặc Map làm root object. Thay vào đó, collection nằm trong một object nghiệp vụ.

Ví dụ:

    public class Department {
        private List<Employee> employees;

        public List<Employee> getEmployees() {
            return employees;
        }
    }

Nếu Department là root object, có thể viết:

    employees.size()
    employees.isEmpty()
    employees.empty

Nếu object được đặt trong variable:

    #department.employees.size()
    #department.employees.isEmpty()

Property employees được đọc trước, sau đó method size() hoặc isEmpty() được gọi trên collection trả về.

Nếu Department hoặc employees có thể null, hãy dùng null-safe navigation tại từng bước:

    #department?.employees?.size()

    #department?.employees?.isEmpty()

Nếu department null, bước truy cập employees trả về null. Dấu ?. tiếp theo bảo vệ thao tác gọi method trên employees.

Không nên chỉ đặt null-safe operator ở đầu đường dẫn rồi giả định mọi bước phía sau tự động an toàn.

## 10. Xử lý null và collection rỗng

Null và collection rỗng là hai trạng thái khác nhau:

- Null: chưa có object collection để truy cập.
- Collection rỗng: object tồn tại nhưng không chứa phần tử.
- Collection có phần tử: object tồn tại và size lớn hơn 0.

Ví dụ:

    #members == null
    #members.isEmpty()
    #members.size() == 0

Ba biểu thức kiểm tra ba điều kiện khác nhau. Nếu members là null, gọi isEmpty() hoặc size() trực tiếp có thể gây evaluation error.

Có thể dùng safe navigation:

    #members?.isEmpty()
    #members?.size()

Khi members null, các expression null-safe trả về null.

Nếu muốn số lượng mặc định bằng 0:

    #members?.size() ?: 0

Elvis chọn 0 khi kết quả bên trái là null. Nếu members tồn tại và rỗng, size() vốn đã trả về 0. Nếu có phần tử, kích thước thật được giữ nguyên.

Nếu muốn coi null cũng như collection rỗng khi kiểm tra trạng thái:

    #members == null or #members.isEmpty()

Hoặc dùng safe navigation với giá trị mặc định:

    #members?.empty ?: true

Khi members null hoặc rỗng, kết quả là true. Khi collection có phần tử, empty là false và Elvis giữ nguyên false.

## 11. Đọc các thuộc tính khác trên Map và Collection

Ngoài size và empty, object Map hoặc Collection còn cung cấp nhiều method hữu ích.

Với Map:

    #settings.keySet()
    #settings.values()
    #settings.entrySet()
    #settings.containsKey('theme')
    #settings.containsValue('dark')

Với Collection:

    #members.contains('Lan')
    #members.iterator()
    #members.toArray()

Các method này được gọi theo cú pháp method invocation. Khả năng gọi phụ thuộc vào MethodResolver và cấu hình EvaluationContext.

Không nên nhầm tên method với property. Ví dụ keySet() là method trả về tập key của Map; keySet không phải property chung được đảm bảo tồn tại trên mọi object.

Với Map, nếu cần lấy một value theo key, dùng:

    #settings['theme']

Nếu cần đếm số entry, dùng:

    #settings.size()

Hai biểu thức có mục đích khác nhau.

## 12. Property JavaBean trên collection tùy chỉnh

Một class tự viết có thể định nghĩa getter riêng để cung cấp property thuận tiện cho SpEL.

Ví dụ:

    public class MemberGroup {
        private List<Member> members;

        public List<Member> getMembers() {
            return members;
        }

        public int getSize() {
            return members == null ? 0 : members.size();
        }

        public boolean isEmpty() {
            return members == null || members.isEmpty();
        }
    }

Với object MemberGroup, các property sau có thể được truy cập:

    #group.size
    #group.empty

Ở đây size là property hợp lệ vì class có getSize(). empty là property hợp lệ vì class có isEmpty().

Điều này khác với List chuẩn:

    #members.size

List không có getSize(), vì vậy SpEL không thể suy ra property size chỉ từ method size().

Nếu class tùy chỉnh vừa có property getter vừa có method trùng ý nghĩa, hãy chọn một cách truy cập thống nhất để biểu thức dễ hiểu.

## 13. Chi phí khi gọi size và empty

Với các implementation phổ biến như ArrayList, HashSet và HashMap, size() và isEmpty() thường đọc một bộ đếm nội bộ hoặc trạng thái có sẵn nên rất nhanh.

Tuy nhiên, không nên giả định mọi implementation Collection đều có chi phí O(1). Collection tùy chỉnh có thể tính kích thước bằng cách duyệt dữ liệu hoặc thực hiện công việc bổ sung.

Một số lưu ý:

- Gọi size() nhiều lần trên cùng collection thường không cần thiết nếu dữ liệu không thay đổi.
- isEmpty() thường thể hiện ý định rõ hơn khi chỉ cần biết collection có phần tử hay không.
- Đừng dùng size() để kiểm tra rỗng nếu isEmpty() đã thể hiện trực tiếp điều kiện.
- Truy cập size sau selection có thể phải tạo collection trung gian.
- Nếu collection được tải từ ORM, việc truy cập hoặc duyệt có thể kích hoạt tải dữ liệu tùy mapping và trạng thái persistence context.
- Không gọi method có I/O hoặc side effect trong biểu thức chỉ để kiểm tra trạng thái collection.

Ví dụ:

    #members.size() > 0

có thể viết rõ hơn là:

    !#members.isEmpty()

Hai biểu thức thể hiện cùng điều kiện khi members không null, nhưng isEmpty() diễn đạt trực tiếp mục tiêu.

## 14. Lỗi thường gặp

| Biểu thức hoặc tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| #members.size | List không có getter getSize() | Dùng #members.size() |
| #members.isEmpty | Thiếu dấu ngoặc gọi method hoặc property name chưa đúng | Dùng #members.isEmpty() hoặc #members.empty |
| #array.size() | Array không có method size() | Dùng #array.length |
| #string.size() | String không có method size() | Dùng #string.length() |
| #members.isEmpty() khi members null | Gọi method trên null | Kiểm tra null hoặc dùng #members?.isEmpty() |
| #settings.size khi muốn đếm entry | Đang truy cập property size | Dùng #settings.size() |
| #settings['size'] khi muốn đếm entry | Đang đọc key size | Dùng #settings.size() |
| SimpleEvaluationContext không cho gọi method | Method resolution chưa được bật | Dùng property accessor phù hợp hoặc cấu hình method resolver theo nhu cầu |

Khi gặp lỗi, hãy kiểm tra loại object thực tế, method có tồn tại không, property accessor có hỗ trợ không và EvaluationContext có cho phép method resolution hay không.

## 15. Những điểm cần nhớ

- Collection và Map dùng size() để lấy số phần tử hoặc số entry.
- Collection và Map dùng isEmpty() để kiểm tra rỗng.
- Trong reflective property access theo JavaBean, empty có thể được đọc qua getter isEmpty().
- List chuẩn không có property size; dùng size() thay cho size.
- Array dùng property length, không có size() hoặc isEmpty().
- String dùng length() và isEmpty().
- Map key được truy cập bằng indexer, ví dụ map['size']; method size() đếm entry.
- Property và method access phụ thuộc vào accessor/resolver của EvaluationContext.
- Null khác collection rỗng; dùng safe navigation hoặc kiểm tra null trước khi gọi method.
- Khi chỉ cần kiểm tra có phần tử hay không, isEmpty() thể hiện ý định tốt hơn size() > 0.
- Với selection trên collection lớn, hãy cân nhắc chi phí tạo collection kết quả trước khi gọi size().

Khi viết expression, hãy xác định kiểu dữ liệu trước: Collection, Map, array hay String. Sau đó chọn đúng API size(), isEmpty(), length hoặc property getter. Phân biệt rõ method invocation với property access giúp tránh lỗi evaluation và làm biểu thức dễ đọc hơn.

## Tài liệu tham khảo

- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Reference — Evaluation and EvaluationContext: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework source — ReflectivePropertyAccessor: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/support/ReflectivePropertyAccessor.java
