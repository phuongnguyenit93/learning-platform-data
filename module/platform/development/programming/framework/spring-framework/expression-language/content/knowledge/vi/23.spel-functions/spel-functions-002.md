# Method static dùng làm function

SpEL cho phép đăng ký một phương thức static của Java dưới một tên hàm để biểu thức gọi lại bằng cú pháp #functionName(...). Cách này hữu ích khi một quy tắc cần tái sử dụng logic Java, chẳng hạn chuẩn hóa mã, kiểm tra định dạng hoặc tính một giá trị theo tham số. Phần Java giữ thuật toán; biểu thức SpEL chỉ gọi hàm với các đối số cần thiết.

Cần phân biệt function đã đăng ký với lời gọi phương thức static trực tiếp qua type reference. Cả hai đều có thể gọi static method, nhưng cách khai báo và cách viết trong biểu thức khác nhau: function dùng tên bí danh trong context, còn lời gọi trực tiếp dùng T(Type).method(...).

## 1. Function trong SpEL là gì?

Function là một phương thức Java được đưa vào EvaluationContext dưới một tên để biểu thức SpEL có thể gọi. Phương thức được đăng ký phải là static vì SpEL gọi nó mà không cần một object instance làm receiver.

Cú pháp gọi function:

    #functionName(argument1, argument2)

Ví dụ, nếu context đăng ký một function tên normalizeCode, biểu thức có thể gọi:

    #normalizeCode(customer.code)

Tiền tố # cho biết đây là tên function được đăng ký trong context. Các đối số bên trong ngoặc vẫn là biểu thức SpEL, vì vậy có thể lấy dữ liệu từ root object, biến context hoặc kết quả của một phép tính khác.

Function trả về giá trị giống một lời gọi phương thức thông thường. Giá trị trả về có thể tiếp tục được dùng trong so sánh, phép nối chuỗi, toán tử điều kiện, selection hoặc projection.

Ví dụ:

    #normalizeCode(customer.code) == 'AB-123'

Hoặc dùng function trong projection:

    lines.![#normalizeCode(product.sku)]

Trong biểu thức thứ hai, function được gọi một lần cho mỗi phần tử của collection.

## 2. Chuẩn bị một static method trong Java

Nên đặt các hàm dùng cho biểu thức trong một utility class có phương thức public static. Ví dụ:

    public final class SpelFunctions {

        private SpelFunctions() {
        }

        public static String normalizeCode(String value) {
            if (value == null) {
                return null;
            }
            return value.trim().toUpperCase(Locale.ROOT);
        }

        public static boolean hasPrefix(
                String value, String prefix) {
            return value != null
                    && prefix != null
                    && value.startsWith(prefix);
        }
    }

Lớp này cung cấp hai hàm:

- normalizeCode loại bỏ khoảng trắng ở hai đầu và chuyển mã thành chữ hoa ổn định theo Locale.ROOT.
- hasPrefix kiểm tra chuỗi có bắt đầu bằng tiền tố đã cho hay không.

Constructor được để private để ngăn việc tạo instance không cần thiết. Các method được khai báo static nên có thể được gọi trực tiếp mà không cần tạo SpelFunctions object.

Một function tốt thường có đầu vào và đầu ra rõ ràng, ít phụ thuộc vào trạng thái bên ngoài và có hành vi dễ kiểm thử. Nếu cần truy cập database, gửi thông báo hoặc thay đổi trạng thái hệ thống, hãy cân nhắc đặt hành động đó trong service Java thay vì đăng ký nó như một function dùng trong biểu thức.

## 3. Đăng ký Method bằng StandardEvaluationContext

SpEL sử dụng đối tượng java.lang.reflect.Method để đại diện cho phương thức cần đăng ký. Có thể lấy Method bằng reflection, sau đó gọi registerFunction():

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction(
            "normalizeCode", normalizeMethod);

getMethod tìm một public method theo tên và danh sách kiểu tham số chính xác. Trong ví dụ, method có tên normalizeCode và nhận một tham số String.

registerFunction gắn Method đó với bí danh normalizeCode trong EvaluationContext. Sau khi đăng ký, biểu thức gọi bằng tiền tố #:

    #normalizeCode(customer.code)

Có thể đăng ký thêm function khác:

    Method prefixMethod =
            SpelFunctions.class.getMethod(
                    "hasPrefix", String.class, String.class);

    context.registerFunction("hasPrefix", prefixMethod);

Biểu thức gọi function hai đối số:

    #hasPrefix(customer.code, 'AB-')

Tên function trong biểu thức phải khớp với tên đã đăng ký. Việc đổi tên bí danh trong context mà không đổi biểu thức, hoặc ngược lại, sẽ khiến SpEL không tìm thấy function.

## 4. Đánh giá function bằng ExpressionParser

Ví dụ hoàn chỉnh:

    ExpressionParser parser = new SpelExpressionParser();

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction(
            "normalizeCode", normalizeMethod);

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

    String normalizedCode =
            expression.getValue(context, String.class);

Quy trình gồm các bước:

1. Java lấy Method đại diện cho static method.
2. EvaluationContext đăng ký Method dưới tên normalizeCode.
3. ExpressionParser phân tích chuỗi SpEL.
4. getValue đánh giá biểu thức với root object order.
5. SpEL gọi function với giá trị customer.code và trả kết quả về cho Java.

Biểu thức không cần biết class SpelFunctions nằm ở package nào. Nó chỉ cần biết tên function đã được context cung cấp. Đây là ưu điểm khi muốn dùng một bí danh ổn định trong nhiều rule.

Nếu method có thể ném checked exception, cần xử lý exception trong method hoặc thiết kế lớp bao phù hợp. Khi function phát sinh lỗi trong lúc đánh giá, SpEL thường bọc lỗi thành exception thuộc nhóm lỗi đánh giá biểu thức; ứng dụng nên ghi nhận nguyên nhân gốc và xử lý theo chính sách của mình.

## 5. Dùng setVariable với Method

Ngoài registerFunction(), StandardEvaluationContext cũng cho phép đăng ký Method như một biến:

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    context.setVariable("normalizeCode", normalizeMethod);

Khi biến có giá trị là một đối tượng Method, SpEL có thể gọi nó theo cú pháp function:

    #normalizeCode(customer.code)

Cách này hữu ích khi ứng dụng muốn quản lý function trong cùng cơ chế setVariable() với các dữ liệu khác. registerFunction() diễn đạt rõ ý định đăng ký một function; setVariable() cung cấp cách đăng ký tổng quát hơn.

Không nên đăng ký cùng một tên cho nhiều mục đích khác nhau. Function và biến cùng nằm trong namespace biến của context; việc ghi đè tên có thể làm biểu thức gọi sai đối tượng hoặc không còn gọi được function mong muốn.

Khi đọc code cũ, có thể gặp cả hai cách đăng ký. Hãy kiểm tra giá trị đang được đặt trong context và phiên bản Spring của ứng dụng trước khi thay đổi API.

## 6. Function khác với lời gọi static method qua T(...)

SpEL có thể gọi static method trực tiếp mà không đăng ký function. Cách viết là dùng type reference T(...) rồi gọi phương thức:

    T(java.lang.Math).max(10, 20)

Với utility class của ứng dụng:

    T(com.example.rules.SpelFunctions)
        .normalizeCode(customer.code)

Đây là method invocation trên một kiểu được phân giải bởi TypeLocator. Biểu thức phải biết tên lớp; với lớp ngoài java.lang, thường cần tên đầy đủ hoặc cấu hình package prefix phù hợp.

Trong khi đó, function đã đăng ký được gọi bằng bí danh:

    #normalizeCode(customer.code)

So sánh:

| Cách gọi | Ví dụ | Cần đăng ký Method trong context? |
|---|---|---|
| Function đã đăng ký | #normalizeCode(customer.code) | Có |
| Static method qua type reference | T(com.example.rules.SpelFunctions).normalizeCode(customer.code) | Không, nhưng TypeLocator phải phân giải được lớp |

Dùng function khi muốn biểu thức phụ thuộc vào một tên hàm ngắn, ổn định và được ứng dụng chủ động cho phép. Dùng T(Type).method(...) khi muốn gọi trực tiếp một static method và chấp nhận để tên lớp xuất hiện trong biểu thức.

Hai cách đều cần được giới hạn quyền khi biểu thức có thể đến từ nguồn bên ngoài.

## 7. Đối số và kiểu dữ liệu của function

Đối số của function là các biểu thức SpEL. Chúng có thể là property của root object, biến context, literal hoặc kết quả của function khác.

Ví dụ:

    #hasPrefix(customer.code, #requiredPrefix)

Trong đó customer.code là property của root object, còn requiredPrefix là biến đã đăng ký:

    context.setVariable("requiredPrefix", "AB-");

Có thể truyền literal trực tiếp:

    #hasPrefix(customer.code, 'AB-')

Hoặc dùng kết quả của một phép tính:

    #calculateDiscount(order.total, #discountRate)

SpEL phải tìm được Method phù hợp với số lượng và kiểu đối số. Method được đăng ký bằng Method object đã gắn với một chữ ký cụ thể. Nếu class có nhiều overload cùng tên, hãy lấy đúng Method với danh sách kiểu tham số mong muốn.

Ví dụ lấy overload nhận hai String:

    Method method = SpelFunctions.class.getMethod(
            "hasPrefix", String.class, String.class);

Đừng dựa vào tên method đơn lẻ để mô tả overload. Nếu có nhiều cách xử lý đầu vào, có thể đăng ký các function bí danh riêng hoặc tạo một static wrapper method có chữ ký rõ ràng.

SpEL có cơ chế chuyển đổi kiểu trong các ngữ cảnh gọi method phù hợp, nhưng không nên dựa vào chuyển đổi ngầm để che giấu dữ liệu đầu vào sai định dạng. Hãy truyền kiểu rõ ràng và kiểm tra giá trị ở biên của ứng dụng.

## 8. Dùng function trong selection và projection

Function đã đăng ký trong context có thể được gọi bên trong selection và projection. Ví dụ, lọc các dòng hàng có mã sản phẩm bắt đầu bằng tiền tố cấu hình:

    lines.?[#hasPrefix(product.sku, #requiredPrefix)]

Sau đó lấy tên của những sản phẩm phù hợp:

    lines.?[#hasPrefix(product.sku, #requiredPrefix)]
         .![product.name]

Có thể chuẩn hóa mã cho từng dòng hàng:

    lines.![#normalizeCode(product.sku)]

Trong mỗi lần gọi, property không có tiền tố như product.sku được đọc từ phần tử hiện tại của collection; function được phân giải theo tên đã đăng ký trong context.

Nếu function cần dữ liệu của root object, hãy truyền dữ liệu đó như một đối số:

    lines.![#formatLine(product.name, #root.currency)]

Function không tự nhận root object hoặc #this làm tham số ngầm. Các giá trị cần thiết phải được đưa vào danh sách đối số một cách tường minh.

## 9. Xử lý null và kết quả trả về

Function nên xác định rõ cách xử lý đầu vào null. Ví dụ normalizeCode ở trên trả về null khi value là null. Nếu nghiệp vụ cần dùng giá trị mặc định, có thể kết hợp function với Elvis:

    #normalizeCode(customer?.code) ?: 'UNKNOWN'

Null-safe navigation bảo vệ việc đọc code nếu customer có thể null. Function nhận kết quả của biểu thức đó; nếu nhận null thì trả null. Elvis sau đó cung cấp UNKNOWN.

Cần phân biệt:

- Nếu customer null và biểu thức dùng customer.code trực tiếp, lỗi có thể xảy ra trước khi function được gọi.
- Nếu dùng customer?.code, đối số có thể là null.
- Nếu function không chấp nhận null, cần kiểm tra đầu vào hoặc bảo đảm điều kiện trước khi gọi.
- Nếu function trả null, biểu thức bên ngoài có thể dùng Elvis hoặc điều kiện để xử lý.

Với tham số primitive như int hoặc boolean, null không thể truyền trực tiếp thành giá trị primitive. Nếu dữ liệu có thể thiếu, cân nhắc dùng wrapper type như Integer hoặc Boolean và xác định quy tắc null rõ ràng.

## 10. Function nên thuần và có trách nhiệm hẹp

Function được gọi trong lúc SpEL đánh giá biểu thức. Nếu một function thực hiện side effect, cùng một biểu thức có thể gây thay đổi trạng thái mỗi khi được đánh giá lại.

Ví dụ, một hàm chuẩn hóa chuỗi hoặc tính điểm thường dễ dự đoán:

    #normalizeCode(customer.code)
    #calculateRiskScore(order.total, #customerTier)

Một hàm gửi email, ghi database hoặc trừ tiền có thể tạo ra hành động khó kiểm soát nếu biểu thức được đánh giá nhiều lần, được gọi trong vòng lặp hoặc được kiểm tra lại trong một luồng xử lý.

Nên ưu tiên function:

- Có đầu vào và đầu ra rõ ràng.
- Không phụ thuộc vào trạng thái mutable bên ngoài.
- Không thực hiện I/O hoặc thay đổi dữ liệu nghiệp vụ.
- Có thể kiểm thử độc lập bằng unit test Java.
- Có giới hạn chi phí tính toán hợp lý.

Nếu cần thực hiện hành động nghiệp vụ, hãy để service Java chịu trách nhiệm về transaction, authorization, retry và logging. SpEL nên quyết định hoặc tính toán điều kiện nhỏ, không nên trở thành nơi điều phối các hành động có side effect.

## 11. Vòng đời Expression và EvaluationContext

Nếu chuỗi biểu thức không đổi, có thể parse một lần rồi tái sử dụng Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

Mỗi lần đánh giá, cung cấp context đã đăng ký function và root object phù hợp:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction("normalizeCode", normalizeMethod);

    String code =
            expression.getValue(context, String.class);

Expression giữ cấu trúc biểu thức đã parse. EvaluationContext cung cấp function, biến và root object cho lần đánh giá hiện tại.

StandardEvaluationContext là đối tượng mutable. Không nên chia sẻ một context đang bị cập nhật giữa nhiều request đồng thời nếu các request có function, biến hoặc root object khác nhau. Hãy tạo context theo lần đánh giá hoặc quản lý việc chia sẻ và đồng bộ hóa có chủ đích.

Cũng không cần parse lại biểu thức chỉ vì root object thay đổi. Có thể dùng cùng Expression với một context mới, miễn là tên function và ý nghĩa biểu thức vẫn tương thích.

## 12. Lỗi thường gặp khi đăng ký static function

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy #normalizeCode(...) | Chưa đăng ký hoặc sai tên function | Kiểm tra registerFunction/setVariable và tên bí danh |
| Reflection báo NoSuchMethodException | Sai tên hoặc kiểu tham số khi lấy Method | Dùng đúng chữ ký trong getMethod |
| Method không thể gọi | Method không public hoặc không static | Đăng ký public static method phù hợp |
| Gọi function với sai số đối số | Biểu thức không khớp chữ ký Method | Kiểm tra số lượng và kiểu tham số |
| Function nhận null ngoài dự kiến | Property đầu vào có thể null | Dùng null-safe navigation và xác định chính sách null |
| Ghi đè function đã đăng ký | Dùng trùng tên trong namespace biến | Đặt tên duy nhất và quản lý đăng ký tập trung |
| Biểu thức lỗi khi gọi function | Lỗi trong chính static method hoặc chuyển đổi đối số | Kiểm tra nguyên nhân gốc và kiểm thử method độc lập |

Khi debug, tách quá trình thành hai bước: trước hết xác nhận Java lấy được đúng Method và đăng ký thành công; sau đó kiểm tra biểu thức SpEL gọi đúng bí danh với đúng đối số. Điều này giúp phân biệt lỗi reflection/cấu hình với lỗi đánh giá biểu thức.

## 13. Giới hạn bảo mật khi đăng ký function

Đăng ký function cho phép biểu thức gọi một phương thức Java đã được chọn. Vì vậy, tập function được đăng ký chính là một phần bề mặt quyền mà biểu thức có thể sử dụng.

Một số nguyên tắc:

- Chỉ đăng ký các method mà rule thực sự cần.
- Ưu tiên public static method nhỏ, thuần và không có side effect.
- Không đăng ký method có thể thực thi lệnh hệ thống, truy cập file tùy ý, gọi mạng hoặc thao tác dữ liệu nhạy cảm nếu không có kiểm soát riêng.
- Không đánh giá chuỗi SpEL tùy ý từ người dùng bên ngoài trong một StandardEvaluationContext có quyền rộng.
- Xác thực đối số bên trong method và thực hiện authorization ở service trước các hành động nhạy cảm.
- Ghi log mã rule và lỗi cần thiết, tránh ghi dữ liệu nhạy cảm hoặc toàn bộ payload.

Function alias không tự tạo sandbox cho Java method. Một method static được đăng ký vẫn chạy với quyền của ứng dụng. Vì vậy, chỉ đăng ký các hàm được phép và kiểm soát nguồn biểu thức.

## 14. Kiểm thử function và biểu thức gọi function

Nên kiểm thử static method độc lập trước, sau đó kiểm thử tích hợp với SpEL.

Với normalizeCode, các trường hợp cần kiểm tra gồm:

- Chuỗi bình thường: xác nhận kết quả được chuẩn hóa.
- Chuỗi có khoảng trắng đầu/cuối: xác nhận trim.
- Chuỗi có chữ thường: xác nhận chuyển thành chữ hoa.
- null: xác nhận chính sách trả về null hoặc giá trị đã quy định.
- Chuỗi rỗng: xác nhận kết quả phù hợp với quy tắc nghiệp vụ.

Ở mức SpEL, kiểm tra thêm:

- Method có được đăng ký dưới đúng bí danh không.
- Biểu thức có parse được không.
- Đối số lấy từ root object và biến context có đúng không.
- Kiểu kết quả từ getValue có phù hợp không.
- Lỗi trong method được truyền ra và xử lý đúng không.
- Function hoạt động đúng khi được gọi trong selection/projection.

Nếu biểu thức được cấu hình bên ngoài, nên kiểm tra và lưu kết quả parse trước khi đưa rule vào luồng xử lý. Một biểu thức parse thành công vẫn có thể lỗi lúc chạy nếu function chưa đăng ký hoặc dữ liệu runtime không phù hợp.

## Kết luận

Một static method có thể được đăng ký trong StandardEvaluationContext dưới dạng function bằng registerFunction(name, method), hoặc được đưa vào context bằng setVariable(name, method). Trong biểu thức, gọi function bằng cú pháp #functionName(arguments). Method cần là static vì SpEL gọi nó mà không có instance receiver.

Cần phân biệt function đã đăng ký với lời gọi static method trực tiếp qua T(Type).method(...). Function phù hợp khi muốn cung cấp bí danh rõ ràng và giới hạn tập hàm mà rule được dùng; lời gọi qua T(...) phù hợp khi biểu thức cần tham chiếu trực tiếp đến lớp. Hãy giữ function nhỏ, dễ kiểm thử, xác định rõ kiểu và null của đối số, quản lý vòng đời EvaluationContext và chỉ đăng ký các method đáng tin cậy.