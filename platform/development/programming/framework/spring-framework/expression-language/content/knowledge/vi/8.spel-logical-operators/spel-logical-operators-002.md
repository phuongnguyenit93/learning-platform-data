# Dạng ký hiệu chữ và dạng ký hiệu toán tử logic

## 1. Hai cách viết cho cùng một phép logic trong SpEL

Spring Expression Language (SpEL) hỗ trợ các toán tử logic để kết hợp điều kiện boolean hoặc phủ định một điều kiện. Với AND, OR và NOT, SpEL cho phép viết theo hai dạng:

- **Dạng chữ:** `and`, `or`, `not`.
- **Dạng ký hiệu:** `&&`, `||`, `!`.

Hai dạng này biểu diễn cùng một ý nghĩa logic. Ví dụ:

    #active and #score >= 80

tương đương với:

    #active && #score >= 80

Tương tự:

    #blocked or #expired

tương đương với:

    #blocked || #expired

Và:

    not #enabled

tương đương với:

    !#enabled

Dạng chữ thường dễ đọc trong biểu thức dài hoặc trong cấu hình do nhiều nhóm cùng quản lý. Dạng ký hiệu ngắn gọn và quen thuộc với người thường viết điều kiện trong Java. Điều quan trọng là hiểu chúng là hai cách biểu diễn toán tử SpEL, không phải hai cơ chế đánh giá khác nhau.

## 2. Bảng đối chiếu các toán tử

| Ý nghĩa | Dạng chữ trong SpEL | Dạng ký hiệu | Kết quả |
| --- | --- | --- | --- |
| AND | `and` | `&&` | true khi cả hai vế đều true |
| OR | `or` | `||` | true khi ít nhất một vế true |
| NOT | `not` | `!` | Đảo giá trị boolean |

Ví dụ nhanh:

    true and true       // true
    true && false       // false
    false or true       // true
    false || false      // false
    not false           // true
    !true               // false

Các ví dụ trên là biểu thức SpEL. Khi đặt trong Java, chúng thường được truyền dưới dạng chuỗi cho parser:

    Expression expression =
        parser.parseExpression("true && false");

Không viết `and` hoặc `or` như toán tử Java trong một biểu thức Java thông thường. Đây là cú pháp mà SpEL hiểu sau khi nhận chuỗi.

## 3. AND: and và &&

AND chỉ cho kết quả true khi cả hai điều kiện đều true.

| A | B | A AND B |
| --- | --- | --- |
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

Hai biểu thức sau tương đương:

    #customer.active and #customer.verified

    #customer.active && #customer.verified

Ví dụ đầy đủ với variables:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "#active && #score >= 80"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    context.setVariable("score", 92);

    Boolean eligible =
        expression.getValue(context, Boolean.class);

Kết quả là `true` vì khách hàng đang hoạt động và điểm số đạt ngưỡng 80.

Có thể đổi biểu thức thành dạng chữ mà không thay đổi ý nghĩa:

    Expression expression = parser.parseExpression(
        "#active and #score >= 80"
    );

Cả hai cách đều yêu cầu các điều kiện được kết hợp cho kết quả boolean phù hợp.

### Short-circuit của AND

AND có hành vi đánh giá ngắn mạch: nếu vế trái đã là false thì kết quả toàn biểu thức chắc chắn là false, nên vế phải không cần được đánh giá.

Ví dụ:

    false and #service.isAvailable()

    false && #service.isAvailable()

Vì vế trái đã false, SpEL không cần gọi biểu thức ở vế phải để quyết định kết quả. Điều này quan trọng khi vế phải có thể truy cập property, gọi method hoặc thực hiện thao tác có chi phí.

Dù có short-circuit, không nên dùng nó để che giấu một biểu thức sai hoặc một lời gọi method không phù hợp. Hãy thiết kế điều kiện sao cho vế trái thể hiện rõ điều kiện cần kiểm tra trước.

## 4. OR: or và ||

OR cho kết quả true khi ít nhất một trong hai điều kiện là true. Chỉ khi cả hai vế đều false thì kết quả mới false.

| A | B | A OR B |
| --- | --- | --- |
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

Hai biểu thức sau tương đương:

    #admin or #owner

    #admin || #owner

Ví dụ:

    Expression expression = parser.parseExpression(
        "#admin || #owner"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("admin", false);
    context.setVariable("owner", true);

    Boolean canManage =
        expression.getValue(context, Boolean.class);

Kết quả là `true` vì người dùng là owner, dù `admin` là false.

### Short-circuit của OR

OR cũng đánh giá ngắn mạch. Nếu vế trái đã true thì toàn biểu thức chắc chắn true, vì vậy vế phải không cần đánh giá.

Ví dụ:

    true or #service.isAvailable()

    true || #service.isAvailable()

Trong hai trường hợp này, SpEL đã biết kết quả là true từ vế trái. Việc bỏ qua vế phải giúp tránh một phép truy cập không cần thiết.

Có thể dùng OR khi một trong nhiều điều kiện đủ để cho phép thao tác. Tuy nhiên, hãy đặt điều kiện theo thứ tự dễ hiểu và không dựa vào side effect của vế phải.

## 5. NOT: not và !

NOT là toán tử một ngôi, nhận một giá trị boolean và đảo kết quả:

- true trở thành false.
- false trở thành true.

Hai cách viết tương đương:

    not #locked

    !#locked

Ví dụ:

    Expression expression =
        parser.parseExpression("!#locked");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("locked", false);

    Boolean canEdit =
        expression.getValue(context, Boolean.class);

Kết quả là `true` vì tài khoản không bị khóa.

NOT áp dụng lên biểu thức theo độ ưu tiên của toán tử. Khi điều kiện phức tạp, dùng ngoặc để làm rõ phạm vi phủ định:

    not (#admin or #owner)

    !(#admin || #owner)

Hai cách viết trên phủ định toàn bộ kết quả của phép OR. Nếu viết:

    !#admin || #owner

thì chỉ phủ định `#admin` trước khi thực hiện OR với `#owner`. Đây là một logic khác.

## 6. Độ ưu tiên và dấu ngoặc

Khi kết hợp nhiều toán tử, SpEL áp dụng độ ưu tiên. Với các toán tử logic đang xét, thứ tự dễ nhớ là:

1. NOT (`not` hoặc `!`) được xử lý trước.
2. AND (`and` hoặc `&&`) được xử lý trước OR.
3. OR (`or` hoặc `||`) được xử lý sau cùng.

Ví dụ:

    #active and #score >= 80 or #admin

được hiểu tương đương về logic với:

    (#active && (#score >= 80)) || #admin

Nếu `#admin` là true, điều kiện tổng thể có thể true dù khách hàng không active hoặc điểm chưa đạt. Nếu yêu cầu nghiệp vụ là người dùng phải active và (đạt điểm hoặc là admin), cần viết rõ:

    #active and (#score >= 80 or #admin)

Dấu ngoặc giúp biểu diễn chính xác nhóm điều kiện. Không nên dựa vào việc người đọc tự suy ra ý định từ một chuỗi dài.

Một ví dụ khác:

    not #suspended and (#verified or #admin)

Điều kiện này yêu cầu tài khoản không bị đình chỉ và đồng thời phải được xác minh hoặc là admin.

Dạng ký hiệu tương ứng:

    !#suspended && (#verified || #admin)

## 7. Kết hợp dạng chữ và dạng ký hiệu

Vì các cặp là cách viết tương đương, một biểu thức có thể dùng cả dạng chữ lẫn dạng ký hiệu:

    #active and #score >= 80 || #admin

Về cú pháp, các toán tử này vẫn biểu diễn AND và OR. Tuy nhiên, trộn hai phong cách trong cùng một biểu thức có thể khiến người đọc khó quét và khó review.

Nên chọn một phong cách thống nhất cho một biểu thức hoặc một nhóm cấu hình:

Dạng chữ:

    #active and (#verified or #admin)

Dạng ký hiệu:

    #active && (#verified || #admin)

Nếu nhóm phát triển ưu tiên biểu thức dễ đọc trong file cấu hình, dạng chữ có thể phù hợp. Nếu biểu thức ngắn và nhóm đã quen với ký hiệu logic, dạng ký hiệu cũng rõ ràng. Hãy giữ cách viết nhất quán trong cùng một codebase.

## 8. Phân biệt toán tử logic với điều kiện so sánh

Toán tử logic kết hợp các giá trị boolean. Toán tử so sánh tạo ra kết quả boolean để có thể đưa vào AND, OR hoặc NOT.

Ví dụ:

    #age >= 18 and #enabled

Trong đó:

- `#age >= 18` là biểu thức so sánh, trả về boolean.
- `#enabled` là một variable boolean.
- `and` kết hợp hai kết quả boolean.

Dạng ký hiệu:

    #age >= 18 && #enabled

Có thể kết hợp nhiều phép so sánh:

    #age >= 18 and #age <= 65

Hoặc viết với ngoặc:

    (#age >= 18) and (#age <= 65)

Dùng ngoặc giúp người đọc nhìn rõ mỗi vế của phép AND là một điều kiện hoàn chỉnh, đặc biệt khi biểu thức có nhiều toán tử so sánh và số học.

Không nên nhầm `and` với `&` hoặc `or` với `|`. Các toán tử bitwise của ngôn ngữ lập trình và toán tử logic trong SpEL có mục đích khác nhau. Khi viết điều kiện boolean, dùng đúng cặp `and`/`&&` và `or`/`||`.

## 9. Dùng biểu thức trong Spring và Java

SpEL expression thường được tạo từ chuỗi Java. Vì vậy, dấu nháy ngoài cùng thuộc Java string, còn toán tử bên trong thuộc cú pháp SpEL.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        "#account.active && (#account.balance >= #minimum || #account.vip)"
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);
    context.setVariable("minimum", 1_000);

    Boolean permitted =
        expression.getValue(context, Boolean.class);

Cấu trúc này có thể được dùng trong một service hoặc thành phần đánh giá rule. Cần bảo đảm object `account` có các property tương ứng và context cung cấp đúng variables.

Trong annotation hoặc cấu hình Spring có hỗ trợ SpEL, có thể viết biểu thức trực tiếp theo cú pháp của điểm tích hợp. Ví dụ:

    @Value("#{systemProperties['user.name'] != null && systemProperties['user.name'].length() > 0}")
    private boolean hasOperatingSystemUser;

Biểu thức trong `#{...}` được Spring xử lý tại điểm tích hợp. Đừng nhầm cách này với một Java string thông thường.

## 10. Kiểm tra lỗi parsing và evaluation

Lỗi liên quan đến toán tử logic có thể xuất hiện ở hai giai đoạn:

| Giai đoạn | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| Parsing | Thiếu toán hạng sau `and`, đặt sai ngoặc hoặc ghép token không hợp lệ | Kiểm tra cú pháp và vị trí trong chuỗi |
| Evaluation | Variable không tồn tại, property không đọc được hoặc giá trị không chuyển được sang boolean | Kiểm tra context, root object, accessor và kiểu dữ liệu |

Ví dụ lỗi cú pháp:

    parser.parseExpression("#active and");

Biểu thức kết thúc bằng toán tử AND nhưng không có vế phải, nên parser không thể tạo expression hợp lệ.

Ví dụ parse thành công nhưng evaluation có thể thất bại:

    Expression expression =
        parser.parseExpression("#active && #score >= 80");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("active", true);
    // Chưa cung cấp variable score

    Boolean result =
        expression.getValue(context, Boolean.class);

Cú pháp có thể được parse thành công, nhưng khi cần đánh giá `#score`, context không cung cấp variable tương ứng. Hãy phân biệt lỗi này với lỗi parser.

Khi debug, xác định chính xác lỗi xảy ra tại `parseExpression` hay `getValue`. Sau đó kiểm tra từng variable và kiểu dữ liệu của điều kiện.

## 11. Bảo mật khi đánh giá điều kiện logic

Một biểu thức logic vẫn có thể truy cập property, gọi method hoặc sử dụng các khả năng khác được cấp qua evaluation context. Vì vậy, biểu thức do người dùng không tin cậy cung cấp không nên được đánh giá trong một context có quyền rộng.

Các nguyên tắc thực tế:

- Không ghép input không tin cậy trực tiếp vào biểu thức rồi parse và evaluate.
- Chỉ đưa các variables cần thiết vào context.
- Dùng object có phạm vi truy cập phù hợp với rule.
- Giới hạn property accessors và method resolvers khi nghiệp vụ cần kiểm soát quyền.
- Cân nhắc `SimpleEvaluationContext` nếu chỉ cần data binding giới hạn.
- Không dựa vào short-circuit để thay thế kiểm soát quyền truy cập.

Dạng chữ và dạng ký hiệu có cùng ý nghĩa logic, nên đổi `and` thành `&&` không làm biểu thức an toàn hơn. Bảo mật phụ thuộc vào nguồn biểu thức và quyền mà context cấp.

## 12. Những điểm cần nhớ

- `and` tương đương `&&`; cả hai là AND.
- `or` tương đương `||`; cả hai là OR.
- `not` tương đương `!`; cả hai là NOT.
- AND chỉ true khi cả hai vế true; OR true khi ít nhất một vế true; NOT đảo boolean.
- AND và OR có hành vi short-circuit.
- NOT có độ ưu tiên cao hơn AND; AND cao hơn OR.
- Dùng ngoặc để thể hiện rõ nhóm điều kiện và tránh hiểu nhầm.
- Các toán tử logic kết hợp kết quả boolean từ variable hoặc biểu thức so sánh.
- Parsing thành công không bảo đảm evaluation thành công; context vẫn phải cung cấp dữ liệu hợp lệ.
- Hai phong cách viết có cùng ngữ nghĩa; hãy chọn một phong cách nhất quán và giới hạn quyền evaluation phù hợp.

Khi viết rule bằng SpEL, hãy ưu tiên điều kiện dễ đọc, có ngoặc ở những chỗ nhóm logic quan trọng và context chỉ chứa dữ liệu mà rule thực sự cần.
