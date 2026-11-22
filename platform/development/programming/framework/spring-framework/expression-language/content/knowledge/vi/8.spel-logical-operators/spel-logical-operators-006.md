# Phân nhóm điều kiện dài bằng dấu ngoặc trong SpEL

Trong Spring Expression Language (SpEL), toán tử logic như `and`, `or` và `not` kết hợp các biểu thức Boolean thành điều kiện phức tạp. Khi một biểu thức có nhiều nhánh, dấu ngoặc đơn giúp xác định rõ nhóm điều kiện nào phải được đánh giá cùng nhau. Cách phân nhóm rõ ràng giúp tránh hiểu nhầm thứ tự ưu tiên toán tử, đồng thời làm cho biểu thức dễ đọc, kiểm thử và bảo trì hơn.

## 1. Vì sao cần phân nhóm điều kiện?

Một điều kiện nghiệp vụ thường gồm nhiều yêu cầu nhỏ. Ví dụ, người dùng được phép truy cập nếu họ là quản trị viên, hoặc nếu họ là biên tập viên đang hoạt động và thuộc đúng phòng ban:

    #user.role == 'ADMIN' or
        #user.role == 'EDITOR' and
        #user.active and
        #user.department == 'CONTENT'

Biểu thức trên có thể được phân tích theo thứ tự ưu tiên mặc định của toán tử. Tuy nhiên, khi đọc nhanh, người bảo trì có thể không nhận ra ba điều kiện cuối đang tạo thành một nhánh AND. Dấu ngoặc làm ý định hiển thị ngay trong cấu trúc:

    #user.role == 'ADMIN' or
        (
            #user.role == 'EDITOR' and
            #user.active and
            #user.department == 'CONTENT'
        )

Cách viết thứ hai thể hiện hai nhánh rõ ràng: nhánh quản trị viên, hoặc nhánh biên tập viên đáp ứng đầy đủ các yêu cầu còn lại.

## 2. Thứ tự ưu tiên của toán tử logic

Trong SpEL, `and` có độ ưu tiên cao hơn `or`. Toán tử `not` là toán tử một ngôi dùng để phủ định điều kiện. Vì vậy:

    A or B and C

được hiểu tương đương:

    A or (B and C)

Nếu nghiệp vụ muốn nhóm `A or B` trước rồi mới kết hợp với `C`, cần viết rõ:

    (A or B) and C

Hai biểu thức này không tương đương trong mọi trường hợp. Ví dụ, khi A=true, B=false và C=false:

- `A or (B and C)` cho kết quả true.
- `(A or B) and C` cho kết quả false.

Dấu ngoặc vì thế có ý nghĩa về logic, không chỉ là cách trình bày. Chúng ghi lại quy tắc nghiệp vụ mà người viết muốn áp dụng.

## 3. Kết hợp AND và OR theo từng nhóm nghiệp vụ

Một cách tổ chức hữu ích là chia điều kiện dài thành các nhóm có ý nghĩa riêng, sau đó kết hợp các nhóm bằng toán tử cấp cao hơn.

Ví dụ: một đơn hàng được chấp nhận nếu đã thanh toán hoặc được miễn thanh toán, đồng thời tổng tiền đạt ngưỡng:

    (
        #order.status == 'PAID' or
        #order.paymentExempt
    )
    and
    #order.total >= 100

Nhóm đầu tiên mô tả trạng thái thanh toán hợp lệ. Nhóm thứ hai kiểm tra giá trị đơn hàng. Toàn bộ biểu thức chỉ đúng khi một trong hai điều kiện thanh toán đúng và tổng tiền đạt ngưỡng.

Một ví dụ khác gồm nhiều nhóm:

    (
        #user.role == 'ADMIN' or
        (
            #user.role == 'EDITOR' and
            #user.department == 'CONTENT'
        )
    )
    and
    #user.active
    and
    not (#user.suspended)

Có thể đọc biểu thức theo ba phần:

1. Người dùng là ADMIN, hoặc là EDITOR thuộc phòng CONTENT.
2. Người dùng đang hoạt động.
3. Người dùng không bị tạm khóa.

Dấu ngoặc bao quanh nhánh OR để điều kiện `active` và `not suspended` áp dụng cho cả hai loại người dùng.

## 4. Nhóm các điều kiện phủ định bằng NOT

Khi phủ định một điều kiện đơn, có thể viết `not` trước biểu thức Boolean đó. Khi phủ định một nhóm gồm nhiều nhánh, hãy đặt toàn bộ nhóm trong dấu ngoặc:

    not (
        #account.disabled or
        #account.expired
    )

Biểu thức trên có nghĩa tài khoản không bị vô hiệu hóa và cũng chưa hết hạn. Theo luật De Morgan, nó tương đương:

    not #account.disabled and
    not #account.expired

Cả hai cách viết đều có thể diễn đạt cùng một logic, nhưng cách phủ định cả nhóm thường dễ đối chiếu với yêu cầu nghiệp vụ dạng “không thuộc bất kỳ trường hợp nào sau đây”.

Một lỗi dễ gặp là đặt `not` sai phạm vi:

    not #account.disabled or #account.expired

Biểu thức này chỉ phủ định trạng thái disabled, sau đó OR với trạng thái expired. Nó không có nghĩa là tài khoản vừa không disabled vừa chưa expired. Khi ý định là phủ định cả hai trường hợp, cần dùng `not (A or B)` hoặc `not A and not B`.

## 5. Dùng ngoặc lồng nhau cho điều kiện nhiều tầng

Với biểu thức có nhiều tầng AND/OR, mỗi cặp ngoặc nên đại diện cho một quy tắc có thể diễn đạt thành một câu ngắn.

Ví dụ, một giao dịch hợp lệ nếu:

- người tạo là chủ tài khoản hoặc người được ủy quyền;
- tài khoản đang hoạt động và chưa bị khóa;
- giao dịch có số tiền dương, hoặc thuộc nhóm giao dịch miễn phí.

Có thể viết:

    (
        #transaction.ownerId == #currentUser.id or
        #transaction.approvedBy == #currentUser.id
    )
    and
    (
        #account.active and
        not (#account.locked)
    )
    and
    (
        #transaction.amount > 0 or
        #transaction.feeExempt
    )

Các nhóm được nối bằng AND ở cấp ngoài. Bên trong mỗi nhóm, OR hoặc AND mô tả quy tắc riêng. Cấu trúc này giúp người đọc kiểm tra từng phần mà không phải tự suy luận toàn bộ thứ tự ưu tiên.

Không nên lồng ngoặc quá sâu nếu có thể đặt tên cho các điều kiện trung gian trong Java hoặc cung cấp các thuộc tính Boolean đã được tính sẵn trên root object. Dấu ngoặc nên làm sáng tỏ logic; quá nhiều tầng lồng nhau có thể khiến biểu thức khó theo dõi.

## 6. Ví dụ chạy biểu thức trong Java

Có thể phân tích biểu thức một lần rồi đánh giá với EvaluationContext:

    public class User {
        private String role;
        private String department;
        private boolean active;
        private boolean suspended;

        // getters and setters
    }

    User user = new User();
    user.setRole("EDITOR");
    user.setDepartment("CONTENT");
    user.setActive(true);
    user.setSuspended(false);

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("user", user);

    ExpressionParser parser = new SpelExpressionParser();

    Expression accessRule = parser.parseExpression(
            "(#user.role == 'ADMIN' or " +
            "(#user.role == 'EDITOR' and " +
            "#user.department == 'CONTENT')) and " +
            "#user.active and not (#user.suspended)"
    );

    Boolean allowed = accessRule.getValue(context, Boolean.class);

Với dữ liệu mẫu, nhánh EDITOR thuộc CONTENT đúng, người dùng đang active và không suspended, nên kết quả là true.

Khi biểu thức dài, có thể định dạng chuỗi thành nhiều dòng trong mã Java để nhìn rõ các nhóm. Việc xuống dòng và thụt lề chỉ cải thiện khả năng đọc; chính dấu ngoặc trong chuỗi biểu thức mới xác định cách nhóm logic.

## 7. Bảo vệ điều kiện khi dữ liệu có thể null

Một nhóm điều kiện thường truy cập nhiều property trên cùng một đối tượng. Nếu đối tượng gốc có thể null, hãy kiểm tra null trước khi truy cập các property tiếp theo:

    #user != null and
    (
        #user.active and
        (
            #user.role == 'ADMIN' or
            #user.role == 'EDITOR'
        )
    )

Toán tử AND trong SpEL đánh giá có short-circuit: nếu vế trái đã false, vế phải không cần được đánh giá. Vì vậy, điều kiện `#user != null` có thể bảo vệ các truy cập `#user.active` phía sau trong cùng nhánh AND.

Tuy nhiên, short-circuit không thay thế việc xác thực dữ liệu đầu vào. Nếu property có kiểu Boolean nullable và có thể trả về null, hãy quyết định rõ null được xem là false, là lỗi dữ liệu hay cần xử lý riêng. Không nên để ý nghĩa nghiệp vụ phụ thuộc vào một giá trị null không được dự kiến.

## 8. Tổ chức biểu thức dài để dễ bảo trì

Khi biểu thức có nhiều nhóm, hãy áp dụng một số quy tắc thực tế:

- **Mỗi nhóm biểu diễn một ý nghiệp vụ:** ví dụ quyền người dùng, trạng thái tài khoản hoặc điều kiện giá trị.
- **Dùng ngoặc cho mọi nhóm OR nằm trong một chuỗi AND:** điều này làm rõ phạm vi của nhánh thay thế.
- **Đặt ngoặc quanh điều kiện bị phủ định:** viết `not (A or B)` khi phủ định cả nhóm.
- **Giữ cùng một cách thụt lề:** mỗi tầng ngoặc lồng nhau nên có mức thụt lề riêng.
- **Đặt tên cho nhóm phức tạp:** nếu một nhóm cần nhiều dòng giải thích, cân nhắc tính trước thành biến Boolean trong Java rồi đưa vào context.
- **Tránh lặp điều kiện có side effect:** biểu thức logic nên ưu tiên đọc trạng thái; không nên gọi method làm thay đổi dữ liệu hoặc thực hiện thao tác ngoài dự kiến.

Ví dụ dùng các biến Boolean trung gian:

    context.setVariable("hasRequiredRole", hasRequiredRole);
    context.setVariable("accountAvailable", accountAvailable);
    context.setVariable("transactionAllowed", transactionAllowed);

    Boolean allowed = parser.parseExpression(
            "#hasRequiredRole and " +
            "#accountAvailable and " +
            "#transactionAllowed"
    ).getValue(context, Boolean.class);

Cách này giúp SpEL tập trung vào việc kết hợp các điều kiện, còn logic tính từng nhóm được kiểm tra và quản lý trong Java.

## 9. Kiểm thử các nhánh logic

Một biểu thức dài cần được kiểm thử theo từng nhóm và theo các trường hợp biên. Với ví dụ quyền truy cập ở trên, tối thiểu nên kiểm tra:

| Trường hợp | Vai trò | Active | Suspended | Kết quả |
|---|---|---:|---:|---:|
| Quản trị viên hợp lệ | ADMIN | true | false | true |
| Biên tập viên đúng phòng ban | EDITOR / CONTENT | true | false | true |
| Biên tập viên sai phòng ban | EDITOR / SALES | true | false | false |
| Người dùng không hoạt động | EDITOR / CONTENT | false | false | false |
| Người dùng bị tạm khóa | ADMIN | true | true | false |

Ngoài các trường hợp đúng/sai thông thường, nên kiểm tra giá trị null nếu model cho phép null và kiểm tra từng nhánh OR để bảo đảm một nhánh đúng không vô tình bỏ qua điều kiện bắt buộc ở cấp ngoài.

Khi kết quả không như mong đợi, hãy rút gọn biểu thức thành từng nhóm rồi đánh giá riêng. Có thể tạo các Expression nhỏ cho từng nhóm, hoặc tính các biến Boolean trong Java để so sánh với kết quả của biểu thức tổng.

## 10. Ghi nhớ

Dấu ngoặc đơn xác định rõ phạm vi kết hợp của `and`, `or` và `not` trong SpEL. `and` có độ ưu tiên cao hơn `or`, vì vậy hãy đặt ngoặc quanh các nhánh OR khi chúng nằm trong một chuỗi AND. Với điều kiện phủ định nhiều phần, dùng `not (A or B)` để thể hiện chính xác phạm vi phủ định. Chia biểu thức thành các nhóm theo ý nghĩa nghiệp vụ, bảo vệ truy cập property có thể null và kiểm thử từng nhánh giúp điều kiện dài dễ hiểu và đáng tin cậy hơn.
