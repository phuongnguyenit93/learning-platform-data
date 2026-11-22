# Thứ tự ưu tiên giữa NOT, AND và OR trong Spring Expression Language (SpEL)

Trong Spring Expression Language (SpEL), các toán tử logic NOT, AND và OR kết hợp những điều kiện Boolean thành một biểu thức lớn hơn. Khi một biểu thức có nhiều toán tử, thứ tự ưu tiên quyết định phần nào được đánh giá trước và cách các điều kiện được nhóm lại.

Quy tắc cốt lõi là: dấu ngoặc đơn xác định nhóm rõ ràng, NOT tác động lên toán hạng của nó, AND được ưu tiên cao hơn OR. Hiểu đúng thứ tự này giúp biểu thức dễ đọc, tránh kết quả ngoài dự kiến và giảm lỗi khi triển khai các quy tắc nghiệp vụ.

## 1. Ba toán tử logic trong SpEL

SpEL hỗ trợ ba phép logic cơ bản:

| Toán tử | Dạng ký hiệu | Ý nghĩa |
|---|---|---|
| NOT | ! | Đảo giá trị Boolean: true thành false và false thành true. |
| AND | && | Kết quả true khi cả hai toán hạng đều true. |
| OR | \|\| | Kết quả true khi ít nhất một toán hạng là true. |

Ngoài ký hiệu, SpEL cho phép viết toán tử bằng từ khóa:

| Từ khóa | Ký hiệu tương đương |
|---|---|
| not | ! |
| and | && |
| or | \|\| |

Ví dụ:

~~~text
not enabled
!enabled

authenticated and active
authenticated && active

administrator or owner
administrator || owner
~~~

Trong một biểu thức, nên dùng nhất quán một kiểu viết để người đọc nhận ra cấu trúc logic nhanh chóng. Các ví dụ trong bài dùng chủ yếu từ khóa not, and và or.

## 2. Bảng chân trị

Bảng chân trị mô tả kết quả của một toán tử với mọi tổ hợp giá trị Boolean có thể có.

### 2.1. NOT

NOT là toán tử một ngôi: nó chỉ nhận một toán hạng và đảo giá trị đó.

| A | NOT A |
|---|---|
| true | false |
| false | true |

Ví dụ:

~~~text
not locked
!locked
~~~

Nếu locked là true thì not locked trả về false. Nếu locked là false thì kết quả là true.

### 2.2. AND

AND là true khi cả hai toán hạng đều true.

| A | B | A AND B |
|---|---|---|
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

Ví dụ:

~~~text
authenticated and hasPermission
~~~

Điều kiện chỉ đúng khi người dùng đã xác thực và có quyền tương ứng.

### 2.3. OR

OR là true khi ít nhất một trong hai toán hạng là true.

| A | B | A OR B |
|---|---|---|
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

Ví dụ:

~~~text
isAdministrator or isOwner
~~~

Điều kiện đúng khi người dùng là quản trị viên hoặc là chủ sở hữu tài nguyên. Nếu cả hai đều false thì kết quả là false.

## 3. Thứ tự ưu tiên của NOT, AND và OR

Khi một biểu thức có nhiều toán tử logic, SpEL áp dụng thứ tự ưu tiên sau:

1. **Dấu ngoặc đơn:** biểu thức bên trong ngoặc được nhóm rõ ràng và đánh giá trước phần kết hợp bên ngoài.
2. **NOT:** đảo giá trị của toán hạng.
3. **AND:** kết hợp các điều kiện với nhau; được ưu tiên trước OR.
4. **OR:** kết hợp các nhánh điều kiện còn lại.

Có thể ghi nhớ thứ tự logic là:

~~~text
NOT > AND > OR
~~~

Ví dụ:

~~~text
A or B and C
~~~

Biểu thức được nhóm như sau:

~~~text
A or (B and C)
~~~

AND được thực hiện trước OR. Nếu muốn OR được thực hiện trước trong trường hợp cụ thể, hãy dùng ngoặc:

~~~text
(A or B) and C
~~~

Hai biểu thức này có thể cho kết quả khác nhau. Với A=true, B=false, C=false:

- A or (B and C) trả về true.
- (A or B) and C trả về false.

Do đó, không nên đọc một biểu thức dài theo thứ tự từ trái sang phải mà bỏ qua độ ưu tiên của toán tử.

## 4. Cách nhóm biểu thức có NOT, AND và OR

NOT là phép đảo một điều kiện. Khi điều kiện đó là một biểu thức so sánh hoặc gồm nhiều phần, hãy dùng ngoặc để xác định chính xác phần cần đảo.

Ví dụ, nếu muốn kiểm tra tuổi không đạt ngưỡng 18:

~~~text
not (age >= 18)
~~~

Cách viết này thể hiện rõ rằng toàn bộ kết quả so sánh age >= 18 được đảo. Khi có toán tử so sánh kết hợp với NOT, ngoặc giúp tránh cách hiểu mơ hồ và làm rõ ý định của biểu thức.

Ví dụ khác:

~~~text
not locked and enabled
~~~

Theo thứ tự ưu tiên, biểu thức tương đương:

~~~text
(not locked) and enabled
~~~

NOT chỉ đảo locked trước khi kết quả được kết hợp với enabled bằng AND.

Với biểu thức:

~~~text
not locked and enabled or isAdministrator
~~~

Cách nhóm theo thứ tự ưu tiên là:

~~~text
((not locked) and enabled) or isAdministrator
~~~

Nếu yêu cầu nghiệp vụ là chỉ cho phép quản trị viên hoặc người vừa không bị khóa vừa đang bật, có thể viết rõ hơn:

~~~text
isAdministrator or (not locked and enabled)
~~~

Nếu yêu cầu là mọi người đều phải không bị khóa, nhưng quản trị viên được phép bỏ qua điều kiện enabled, biểu thức trên cũng thể hiện đúng cấu trúc đó. Hãy chọn cách nhóm theo ý nghĩa nghiệp vụ rồi dùng ngoặc để mã hóa ý nghĩa đó.

## 5. Dấu ngoặc đơn giúp biểu đạt ý định

Ngoặc đơn có tác dụng nhóm một phần biểu thức thành một đơn vị logic. Chúng đặc biệt hữu ích khi có nhiều nhánh AND và OR.

So sánh hai cách viết:

~~~text
authenticated and administrator or owner
~~~

và:

~~~text
authenticated and (administrator or owner)
~~~

Cách thứ nhất được nhóm thành:

~~~text
(authenticated and administrator) or owner
~~~

Cách thứ hai yêu cầu đã xác thực trước, sau đó phải là quản trị viên hoặc chủ sở hữu.

Ví dụ với authenticated=false, administrator=false, owner=true:

- Cách thứ nhất trả về true vì nhánh owner đúng.
- Cách thứ hai trả về false vì authenticated sai.

Một cặp biểu thức khác:

~~~text
not disabled and active or publicResource
~~~

~~~text
not disabled and (active or publicResource)
~~~

Ở biểu thức đầu, publicResource=true có thể làm toàn bộ biểu thức đúng dù tài nguyên bị disabled. Ở biểu thức sau, disabled=true khiến điều kiện not disabled sai và toàn bộ AND sai.

Khi quy tắc có nhiều điều kiện, nên đặt ngoặc theo từng nhóm nghiệp vụ như trạng thái, quyền truy cập, chủ sở hữu hoặc ngoại lệ. Cách nhóm này làm biểu thức dễ xem xét và dễ thay đổi hơn.

## 6. Ví dụ trong SpEL với root object

Giả sử một ứng dụng có quy tắc truy cập tài nguyên. Người dùng được phép truy cập khi đã xác thực và thuộc một trong các trường hợp: là quản trị viên, hoặc là biên tập viên sở hữu tài nguyên.

~~~java
public class AccessPolicy {
    private final boolean authenticated;
    private final boolean administrator;
    private final boolean editor;
    private final boolean owner;

    public AccessPolicy(
            boolean authenticated,
            boolean administrator,
            boolean editor,
            boolean owner) {
        this.authenticated = authenticated;
        this.administrator = administrator;
        this.editor = editor;
        this.owner = owner;
    }

    public boolean isAuthenticated() {
        return authenticated;
    }

    public boolean isAdministrator() {
        return administrator;
    }

    public boolean isEditor() {
        return editor;
    }

    public boolean isOwner() {
        return owner;
    }
}
~~~

Tạo biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "authenticated and (administrator or (editor and owner))"
);
~~~

Đánh giá biểu thức với dữ liệu:

~~~java
AccessPolicy policy = new AccessPolicy(
        true,   // authenticated
        false,  // administrator
        true,   // editor
        true    // owner
);

Boolean allowed = expression.getValue(policy, Boolean.class);

// allowed == true
~~~

Cách nhóm biểu thức cho thấy:

1. Người dùng phải được xác thực.
2. Sau đó người dùng có thể là quản trị viên.
3. Nếu không phải quản trị viên, người dùng cần đồng thời là biên tập viên và chủ sở hữu.

Nếu thay owner bằng false trong ví dụ, nhánh editor and owner trở thành false. Vì administrator cũng false, phần trong ngoặc false và kết quả cuối cùng false.

Nếu authenticated=false, toàn bộ biểu thức AND cũng false dù các điều kiện quyền phía sau có đúng.

## 7. Ví dụ với NOT và nhiều nhánh OR

Giả sử một chức năng chỉ được bật khi tài khoản không bị khóa và người dùng thuộc một trong các nhóm được phép:

~~~text
not accountLocked and (isAdministrator or isSupport or isOwner)
~~~

Cấu trúc có thể đọc thành:

- Tài khoản phải không bị khóa.
- Người dùng là quản trị viên, nhân viên hỗ trợ hoặc chủ sở hữu.

Nếu không có ngoặc:

~~~text
not accountLocked and isAdministrator or isSupport or isOwner
~~~

thì AND được thực hiện trước OR. Biểu thức tương đương:

~~~text
((not accountLocked) and isAdministrator) or isSupport or isOwner
~~~

Khi đó isSupport=true hoặc isOwner=true có thể làm kết quả đúng ngay cả khi accountLocked=true. Nếu điều này trái với yêu cầu nghiệp vụ, cần nhóm các nhánh OR bằng ngoặc như ví dụ đầu tiên.

## 8. Đánh giá theo từng bước và tính ngắn mạch

AND và OR trong biểu thức logic có hành vi đánh giá ngắn mạch:

- Với AND, nếu toán hạng bên trái là false thì kết quả chắc chắn false. SpEL không cần đánh giá toán hạng bên phải.
- Với OR, nếu toán hạng bên trái là true thì kết quả chắc chắn true. SpEL không cần đánh giá toán hạng bên phải.
- Nếu chưa thể xác định kết quả từ toán hạng bên trái, toán hạng bên phải mới được đánh giá.

Ví dụ:

~~~text
hasProfile and profile.enabled
~~~

Nếu hasProfile=false, phần profile.enabled không cần được đánh giá. Điều này hữu ích khi vế phải phụ thuộc vào một dữ liệu chỉ hợp lệ khi điều kiện ở vế trái đúng.

Ví dụ khác:

~~~text
isAdministrator or user.hasSpecialAccess()
~~~

Nếu isAdministrator=true, SpEL có thể xác định kết quả OR ngay mà không cần gọi phương thức ở vế phải.

Tính ngắn mạch không thay thế việc thiết kế biểu thức an toàn. Hãy sắp xếp điều kiện bảo vệ trước phần có khả năng truy cập dữ liệu null hoặc thực hiện lời gọi phương thức.

## 9. Giá trị Boolean null và điều kiện an toàn

Các toán tử logic cần toán hạng Boolean. Nếu một thuộc tính Boolean có thể nhận null, không nên giả định null tương đương false.

Ví dụ, với thuộc tính enabled kiểu java.lang.Boolean, biểu thức:

~~~text
not enabled
~~~

có thể không đánh giá được khi enabled là null, vì không có giá trị Boolean để đảo.

Có thể kiểm tra giá trị một cách tường minh:

~~~text
enabled == true
enabled == false
enabled != null and enabled
~~~

enabled == true chỉ đúng khi enabled thực sự là Boolean true. Biểu thức enabled != null and enabled tận dụng tính ngắn mạch: nếu enabled là null, vế trái false và vế phải không được đánh giá.

Với các thuộc tính Boolean nullable, cách so sánh tường minh giúp biểu thức dễ hiểu hơn và tránh giả định về dữ liệu.

## 10. Kết hợp toán tử so sánh với NOT, AND và OR

Trong các điều kiện nghiệp vụ, toán tử logic thường kết hợp với so sánh số, chuỗi hoặc trạng thái.

Ví dụ:

~~~text
age >= 18 and accountActive
~~~

~~~text
status == 'APPROVED' or isAdministrator
~~~

~~~text
not (balance < 0) and accountActive
~~~

~~~text
(isPremium or isStaff) and not suspended
~~~

Các phép so sánh tạo ra kết quả Boolean, sau đó NOT, AND hoặc OR kết hợp những kết quả đó. Khi có nhiều phép so sánh và nhánh logic, hãy dùng ngoặc để thể hiện nhóm điều kiện theo đúng yêu cầu.

Một biểu thức có thể parse thành công nhưng vẫn không đánh giá được nếu thuộc tính không tồn tại, kiểu dữ liệu không phù hợp hoặc phương thức cần gọi không truy cập được. Hãy kiểm tra root object và EvaluationContext khi gặp lỗi.

## 11. Những lỗi thường gặp

| Lỗi | Vì sao có vấn đề | Cách xử lý |
|---|---|---|
| Giả định OR được ưu tiên trước AND | AND có độ ưu tiên cao hơn OR. | Thêm ngoặc quanh nhóm OR nếu cần. |
| Viết biểu thức dài mà không nhóm | Người đọc khó nhận ra phạm vi của từng điều kiện. | Dùng ngoặc theo từng nhóm nghiệp vụ. |
| Đảo sai phạm vi bằng NOT | NOT chỉ tác động lên toán hạng của nó. | Đặt ngoặc quanh điều kiện cần phủ định. |
| Dùng null như false | null không phải một giá trị Boolean. | Kiểm tra null hoặc so sánh với true/false. |
| So sánh Boolean với chuỗi 'true' | Chuỗi và Boolean là hai kiểu khác nhau. | Dùng literal true hoặc false. |
| Dùng từ khóa viết hoa tùy tiện | Cú pháp biểu thức cần dùng đúng token toán tử. | Dùng nhất quán not, and, or hoặc ký hiệu tương ứng. |
| Dựa vào thứ tự trái sang phải | Độ ưu tiên của toán tử quyết định cách nhóm. | Phân tích theo NOT, AND, OR và thêm ngoặc. |
| Dùng vế phải có thể lỗi mà không có điều kiện bảo vệ | Vế phải có thể được đánh giá khi chưa thỏa điều kiện cần thiết. | Đặt điều kiện bảo vệ ở vế trái của AND hoặc nhóm lại. |

## 12. Kiểm tra biểu thức khi phát triển

Có thể phân tích biểu thức trước rồi đánh giá với nhiều bộ dữ liệu để xác nhận kết quả:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "authenticated and (administrator or (editor and owner))"
);

Boolean first = expression.getValue(
        new AccessPolicy(true, false, true, true),
        Boolean.class
);

Boolean second = expression.getValue(
        new AccessPolicy(true, false, true, false),
        Boolean.class
);

Boolean third = expression.getValue(
        new AccessPolicy(false, true, true, true),
        Boolean.class
);

// first == true
// second == false
// third == false
~~~

Các trường hợp kiểm tra nên bao gồm:

- Tất cả điều kiện thành phần đều false.
- Chỉ một nhánh OR đúng.
- Một nhánh AND thiếu một điều kiện.
- Điều kiện NOT đổi từ false sang true và ngược lại.
- Các giá trị Boolean nullable nếu mô hình dữ liệu cho phép null.
- Những tổ hợp có ngoặc làm thay đổi kết quả.

Khi cần chẩn đoán, phân biệt lỗi phân tích cú pháp (ParseException) với lỗi đánh giá (EvaluationException). Kiểm tra biểu thức, kiểu dữ liệu của thuộc tính, root object và các thành phần trong EvaluationContext.

## 13. Ghi nhớ

- NOT đảo một giá trị Boolean; AND yêu cầu cả hai vế đúng; OR chỉ cần một vế đúng.
- Có thể viết toán tử bằng từ khóa not, and, or hoặc ký hiệu !, &&, ||.
- Thứ tự ưu tiên logic là NOT trước AND, AND trước OR.
- Dấu ngoặc đơn giúp nhóm điều kiện và ghi đè cách kết hợp mặc định.
- Khi kết hợp so sánh với NOT, hãy đặt ngoặc quanh phép so sánh cần phủ định.
- AND và OR có thể đánh giá ngắn mạch; hãy đặt điều kiện bảo vệ trước biểu thức phụ thuộc dữ liệu.
- Boolean null cần được xử lý tường minh, không tự động coi là false.
- Viết biểu thức theo nhóm nghiệp vụ giúp dễ đọc, kiểm tra và bảo trì.
