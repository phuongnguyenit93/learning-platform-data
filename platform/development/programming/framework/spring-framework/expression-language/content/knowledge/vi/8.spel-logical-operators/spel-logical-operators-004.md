# Short-circuit và ảnh hưởng đến vế phải của biểu thức

Trong SpEL, các toán tử logic AND và OR đánh giá toán hạng theo thứ tự từ trái sang phải và có cơ chế short-circuit. Điều đó có nghĩa là kết quả của vế trái đôi khi đã đủ để xác định kết quả toàn biểu thức; khi ấy SpEL bỏ qua việc đánh giá vế phải.

Cơ chế này ảnh hưởng trực tiếp đến những gì xảy ra trong vế phải. Nếu vế phải gọi method, đọc một thuộc tính có getter gây tác dụng phụ, thực hiện phép gán hoặc gọi một hàm, phần đó có thể không được chạy. Vì vậy, khi viết biểu thức logic, cần xem xét cả giá trị Boolean lẫn hành vi có thể xảy ra trong quá trình đánh giá.

## 1. Short-circuit là gì?

Short-circuit evaluation là cách đánh giá biểu thức logic mà không cần tính mọi toán hạng nếu kết quả đã được quyết định.

Với phép AND:

- Nếu vế trái là false, toàn bộ phép AND chắc chắn là false. Vế phải không cần đánh giá.
- Nếu vế trái là true, cần đánh giá vế phải để biết kết quả cuối cùng.

Với phép OR:

- Nếu vế trái là true, toàn bộ phép OR chắc chắn là true. Vế phải không cần đánh giá.
- Nếu vế trái là false, cần đánh giá vế phải để biết kết quả cuối cùng.

Bảng sau thể hiện điều kiện quyết định:

| Toán tử | Vế trái | Vế phải có được đánh giá? | Kết quả |
|---|---|---|---|
| AND | false | Không | false |
| AND | true | Có | Theo giá trị vế phải |
| OR | true | Không | true |
| OR | false | Có | Theo giá trị vế phải |

Điểm quan trọng là việc bỏ qua vế phải là một phần của ngữ nghĩa đánh giá, không chỉ là một cách tối ưu hiệu năng. Những hành động nằm trong vế phải cũng bị bỏ qua.

## 2. Toán tử logic trong SpEL

SpEL hỗ trợ cách viết từ khóa và dạng ký hiệu cho các phép logic:

| Ý nghĩa | Từ khóa | Ký hiệu |
|---|---|---|
| AND | and | && |
| OR | or | \|\| |
| NOT | not | ! |

Ví dụ:

~~~text
enabled and verified
enabled && verified
cached or loadAvailable()
cached || loadAvailable()
not disabled
!disabled
~~~

Hai cách viết AND và OR có cùng ý nghĩa logic. Hãy chọn một phong cách nhất quán trong cùng một nhóm biểu thức để người đọc dễ theo dõi.

Với AND, vế phải chỉ chạy khi vế trái true. Với OR, vế phải chỉ chạy khi vế trái false. Quy tắc này áp dụng cho biểu thức SpEL được đánh giá, kể cả khi vế phải chứa lời gọi method hoặc phép truy cập thuộc tính.

## 3. Thứ tự đánh giá từ trái sang phải

SpEL đánh giá toán hạng bên trái trước. Sau khi có kết quả bên trái, toán tử logic quyết định có cần đánh giá bên phải hay không.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "false and (10 / 0 > 1)"
);

Boolean result = expression.getValue(Boolean.class);

System.out.println(result); // false
~~~

Vế trái đã là false nên vế phải không được đánh giá. Phép chia cho 0 nằm ở vế phải vì vậy không được thực hiện trong lượt đánh giá này.

Với OR, tình huống tương tự xảy ra khi vế trái true:

~~~java
Expression expression = parser.parseExpression(
        "true or (10 / 0 > 1)"
);

Boolean result = expression.getValue(Boolean.class);

System.out.println(result); // true
~~~

Vế phải bị bỏ qua vì true OR bất kỳ giá trị Boolean nào cũng cho kết quả true.

Không nên dựa vào việc một vế phải đang được bỏ qua để che giấu biểu thức sai hoặc dữ liệu không hợp lệ. Nếu điều kiện bên trái thay đổi, SpEL có thể đánh giá vế phải và khi đó lỗi sẽ xuất hiện.

## 4. Ảnh hưởng đến lời gọi method ở vế phải

Vế phải có thể gọi method trên root object, biến hoặc bean mà context cho phép truy cập. Nếu short-circuit xảy ra, method đó không được gọi.

Giả sử ứng dụng có một đối tượng kiểm tra:

~~~java
public class AccessCheck {

    private final boolean enabled;
    private int auditCalls;

    public AccessCheck(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean recordAudit() {
        auditCalls++;
        return true;
    }

    public int getAuditCalls() {
        return auditCalls;
    }
}
~~~

Có thể đánh giá biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

AccessCheck check = new AccessCheck(false);
EvaluationContext context =
        new StandardEvaluationContext(check);

Expression expression = parser.parseExpression(
        "enabled and recordAudit()"
);

Boolean result = expression.getValue(context, Boolean.class);

System.out.println(result);             // false
System.out.println(check.getAuditCalls()); // 0
~~~

Do enabled là false, SpEL không gọi recordAudit(). Bộ đếm vẫn bằng 0. Nếu enabled là true, method recordAudit() được gọi và kết quả của method quyết định kết quả phép AND.

Đây là điều cần lưu ý khi method có các hành vi như ghi log, tăng bộ đếm, cập nhật trạng thái, gửi thông báo, ghi database hoặc gọi hệ thống bên ngoài. Việc đặt method ở vế phải của AND không đảm bảo nó luôn chạy.

## 5. Ảnh hưởng đến lời gọi method ở vế phải của OR

Với OR, method ở vế phải chỉ chạy khi vế trái false.

Ví dụ, một cache có thể kiểm tra dữ liệu đã sẵn sàng hay chưa:

~~~java
public class CacheProbe {

    private final boolean cached;
    private int remoteCalls;

    public CacheProbe(boolean cached) {
        this.cached = cached;
    }

    public boolean isCached() {
        return cached;
    }

    public boolean loadFromRemote() {
        remoteCalls++;
        return true;
    }

    public int getRemoteCalls() {
        return remoteCalls;
    }
}
~~~

Biểu thức:

~~~java
Expression expression = parser.parseExpression(
        "cached or loadFromRemote()"
);
~~~

Nếu cached là true, kết quả đã được xác định là true và loadFromRemote() không chạy. Nếu cached là false, SpEL mới gọi method ở vế phải.

Điều này có thể hữu ích khi vế phải là một thao tác tốn chi phí và chỉ cần thực hiện khi điều kiện bên trái chưa đáp ứng. Tuy nhiên, nếu vế phải có tác dụng phụ quan trọng, đừng để việc thực hiện nó phụ thuộc vào một điều kiện logic mà người đọc có thể hiểu nhầm.

## 6. Getter và property accessor cũng có thể bị bỏ qua

Không chỉ method được gọi trực tiếp mới có tác dụng phụ. Khi SpEL đọc một thuộc tính, accessor có thể gọi getter trên object. Nếu getter thực hiện truy vấn, tải dữ liệu lazy, ghi log hoặc thay đổi trạng thái, việc đọc thuộc tính cũng có thể tạo ra hành vi quan sát được.

Ví dụ:

~~~text
active and profile.expensiveStatus
~~~

Nếu active là false, SpEL không cần đọc profile.expensiveStatus. Getter hoặc accessor tương ứng không được gọi trong lượt đánh giá đó.

Tương tự:

~~~text
ready or remoteState.available
~~~

Nếu ready là true, SpEL không đọc remoteState.available.

Đây là lý do nên thiết kế getter theo hướng trả về dữ liệu ổn định, ít tác dụng phụ. Một biểu thức logic có thể được đánh giá nhiều lần với các điều kiện khác nhau; nếu getter thực hiện I/O hoặc thay đổi trạng thái, hành vi sẽ khó dự đoán và khó kiểm thử.

## 7. Không đặt tác dụng phụ quan trọng trong vế phải

Short-circuit khiến số lần thực thi vế phải phụ thuộc dữ liệu của vế trái. Vì vậy, không nên dùng biểu thức logic làm nơi bắt buộc thực hiện một hành động quan trọng.

Ví dụ, biểu thức sau có thể không ghi nhận audit:

~~~text
authorized and recordAudit()
~~~

Khi authorized là false, recordAudit() không được gọi. Nếu yêu cầu nghiệp vụ là mọi lần truy cập đều phải ghi audit, hãy thực hiện audit trong Java/service flow riêng, sau đó mới đánh giá điều kiện. Không dùng một toán hạng logic làm cơ chế đảm bảo side effect.

Tương tự, biểu thức:

~~~text
isValid or saveFallback()
~~~

không gọi saveFallback() khi isValid là true. Nếu saveFallback() thực hiện lưu dữ liệu hoặc gửi thông báo, hành động đó chỉ xảy ra trong nhánh mà vế trái false.

Nên giữ các biểu thức SpEL thiên về kiểm tra và tính toán. Các hành động thay đổi trạng thái, I/O và giao tiếp bên ngoài thường phù hợp hơn trong Java service, nơi thứ tự và lỗi có thể được điều khiển rõ ràng.

## 8. Dùng ngoặc để thể hiện nhóm điều kiện

Khi biểu thức có nhiều toán tử AND/OR, ngoặc giúp người đọc xác định nhóm điều kiện và nhánh nào có thể bị short-circuit.

Ví dụ:

~~~text
isAdmin or (isOwner and isActive)
~~~

Nếu isAdmin là true, cả nhóm bên phải bị bỏ qua. Nếu isAdmin là false, SpEL đánh giá nhóm isOwner and isActive. Trong nhóm đó, nếu isOwner là false thì isActive không được đánh giá.

Một ví dụ khác:

~~~text
isEnabled and (hasPermission or isPublic)
~~~

Nếu isEnabled là false, toàn bộ nhóm bên phải bị bỏ qua. Nếu isEnabled là true, SpEL đánh giá hasPermission. Nếu hasPermission là true, isPublic không cần được đánh giá.

Khi biểu thức được dùng trong rule nghiệp vụ, hãy đặt ngoặc ngay cả khi thứ tự ưu tiên của toán tử đã đủ xác định kết quả. Ngoặc giúp người đọc nhìn thấy ranh giới của từng nhánh và dự đoán được lời gọi nào có thể xảy ra.

## 9. Short-circuit không phải cơ chế kiểm soát quyền truy cập

Không nên xem short-circuit là một lớp bảo mật cho biểu thức. Nó chỉ quyết định một toán hạng có được đánh giá trong một lượt cụ thể hay không.

Nếu người dùng có thể chỉnh sửa biểu thức, họ có thể thay đổi vế trái, đảo điều kiện hoặc đưa lời gọi method sang vị trí khác. Một biểu thức có thể bỏ qua vế phải trong một request, nhưng chạy nó trong request khác.

Với biểu thức không đáng tin cậy:

1. Giới hạn root object và dữ liệu mà biểu thức nhìn thấy.
2. Hạn chế method, bean, function và property accessor được phép truy cập.
3. Tránh cấp service có khả năng ghi dữ liệu hoặc gọi hệ thống bên ngoài.
4. Ưu tiên SimpleEvaluationContext cho các nhu cầu data binding giới hạn.
5. Không dựa vào một điều kiện Boolean để ngăn người dùng gọi một method nhạy cảm ở vế phải.
6. Thực hiện kiểm tra quyền và side effect quan trọng trong Java/service layer.

Việc short-circuit có thể tránh một lời gọi không cần thiết, nhưng không thay thế authorization hoặc sandbox.

## 10. Mỗi lần getValue có thể có nhánh thực thi khác nhau

Expression sau khi parse có thể được tái sử dụng. Tuy nhiên, mỗi lần gọi getValue, SpEL vẫn đánh giá biểu thức với dữ liệu/context của lần gọi đó.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "enabled and verify()"
);

Boolean first = expression.getValue(
        new StandardEvaluationContext(new Probe(false)),
        Boolean.class
);

Boolean second = expression.getValue(
        new StandardEvaluationContext(new Probe(true)),
        Boolean.class
);
~~~

Ở lần đầu, vế phải bị bỏ qua. Ở lần thứ hai, vế phải được đánh giá. Việc tái sử dụng Expression không có nghĩa kết quả hoặc trạng thái short-circuit được lưu lại từ lần trước.

Điều này đặc biệt quan trọng khi context chứa biến hoặc root object thay đổi theo request. Hãy tạo context phù hợp cho từng lượt đánh giá và tránh dùng chung một object mutable nếu nhiều luồng có thể đánh giá biểu thức đồng thời.

## 11. Cách kiểm tra hành vi short-circuit

Khi vế phải có thể tạo side effect, hãy kiểm tra cả kết quả biểu thức lẫn việc method có thực sự được gọi hay không. Một kết quả Boolean đúng chưa đủ chứng minh nhánh được thực thi theo ý muốn.

Một cách đơn giản là dùng method kiểm thử có bộ đếm:

~~~java
public class Probe {

    private final boolean left;
    private int calls;

    public Probe(boolean left) {
        this.left = left;
    }

    public boolean isLeft() {
        return left;
    }

    public boolean verify() {
        calls++;
        return true;
    }

    public int getCalls() {
        return calls;
    }
}
~~~

Với biểu thức:

~~~text
left and verify()
~~~

hãy kiểm tra hai trường hợp:

| Giá trị left | Kết quả biểu thức | Số lần verify() được gọi |
|---|---|---|
| false | false | 0 |
| true | true | 1 |

Với biểu thức:

~~~text
left or verify()
~~~

kết quả kiểm tra đảo lại:

| Giá trị left | Kết quả biểu thức | Số lần verify() được gọi |
|---|---|---|
| true | true | 0 |
| false | true | 1 |

Có thể bổ sung trường hợp vế phải trả về false để xác nhận kết quả AND/OR, cũng như trường hợp vế phải ném exception để chứng minh exception chỉ xuất hiện khi nhánh đó thực sự được đánh giá.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Method ở vế phải không chạy | Vế trái đã quyết định kết quả phép AND/OR | Kiểm tra giá trị vế trái và quy tắc short-circuit |
| Audit hoặc counter không tăng | Side effect được đặt trong nhánh có thể bị bỏ qua | Chuyển hành động bắt buộc sang Java/service flow |
| Exception ở vế phải chỉ xuất hiện đôi khi | Vế phải chỉ được đánh giá khi cần | Kiểm tra dữ liệu khiến nhánh được thực thi |
| Getter không được gọi | Property access nằm ở vế phải bị short-circuit | Không dựa vào getter để thực hiện tác vụ bắt buộc |
| Biểu thức nhiều AND/OR khó hiểu | Nhóm điều kiện và thứ tự đánh giá không rõ | Dùng ngoặc và chia biểu thức thành các phần có tên |
| Cho rằng method bị bỏ qua là đã được bảo vệ | Short-circuit phụ thuộc giá trị đầu vào | Giới hạn quyền trong EvaluationContext và service layer |
| Kết quả khác giữa hai lần gọi | Root object hoặc biến thay đổi giữa các lượt đánh giá | Kiểm tra context và dữ liệu đầu vào của từng lần getValue |

## 13. Ghi nhớ

Short-circuit trong SpEL làm cho AND bỏ qua vế phải khi vế trái false, và OR bỏ qua vế phải khi vế trái true. Việc bỏ qua này áp dụng cho toàn bộ quá trình đánh giá vế phải, bao gồm method call, getter, accessor, phép gán và các hành vi có thể tạo side effect.

Hãy đặt điều kiện có thể quyết định kết quả ở vế trái, dùng ngoặc để làm rõ các nhánh, và giữ biểu thức chủ yếu phục vụ kiểm tra dữ liệu. Nếu một hành động bắt buộc phải xảy ra, hãy thực hiện nó trong Java/service flow riêng thay vì đặt nó ở vế phải của phép logic.