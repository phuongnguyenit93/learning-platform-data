# Tham chiếu java.lang tự động

Trong SpEL, toán tử tham chiếu kiểu T(...) cho phép biểu thức truy cập một lớp Java theo tên kiểu. Thông thường, tên lớp cần được viết đầy đủ, chẳng hạn T(java.time.LocalDate). Tuy nhiên, với StandardEvaluationContext và StandardTypeLocator mặc định, package java.lang đã được đăng ký sẵn. Vì vậy, có thể tham chiếu các kiểu phổ biến như String, Integer hoặc Math mà không cần viết tiền tố java.lang.

Cơ chế này giúp biểu thức ngắn gọn hơn, nhưng không có nghĩa SpEL tự động import mọi package như câu lệnh import trong mã Java. Cần hiểu phạm vi của package mặc định, cách phân giải tên kiểu và cách đăng ký package khác khi ứng dụng thực sự cần.

## 1. Type reference T(...) là gì?

T(...) là toán tử tham chiếu kiểu của SpEL. Phần nằm trong ngoặc là tên lớp mà EvaluationContext sẽ phân giải thành một đối tượng Class.

Ví dụ:

    T(String)
    T(Integer)
    T(Math)

Với các kiểu thuộc package khác:

    T(java.time.LocalDate)
    T(java.math.BigDecimal)
    T(com.example.domain.Order)

Kết quả của một type reference là tham chiếu đến kiểu Java, không phải một instance mới của lớp đó. Từ tham chiếu kiểu, SpEL có thể truy cập thành viên static hoặc sử dụng kiểu trong một số phép kiểm tra khác.

Ví dụ, đọc hằng số PI:

    T(Math).PI

Gọi phương thức static:

    T(String).valueOf(123)

Kiểm tra kiểu runtime:

    #value instanceof T(String)

Nếu muốn tạo một đối tượng mới, cú pháp là new, không phải chỉ T(...):

    new java.math.BigDecimal('125.50')

Do đó, cần phân biệt ba ý định: T(...) tham chiếu đến lớp, dấu chấm sau type reference truy cập thành viên của lớp, còn new gọi constructor để tạo instance.

## 2. Vì sao java.lang được tham chiếu tự động?

java.lang là package chứa nhiều kiểu nền tảng của Java, chẳng hạn:

- String, Object và Class.
- Các lớp wrapper như Integer, Long, Double và Boolean.
- Math, System và Runtime.
- Các kiểu ngoại lệ và nhiều lớp tiện ích nền tảng khác.

Trong StandardEvaluationContext, TypeLocator mặc định là StandardTypeLocator. Khi được khởi tạo theo cấu hình mặc định, locator này đã đăng ký package prefix java.lang. Vì vậy, khi gặp một tên kiểu ngắn như String, nó thử phân giải tên đó trong package đã đăng ký.

Ví dụ hai cách viết sau cùng tham chiếu đến lớp String:

    T(String)

    T(java.lang.String)

Cách viết ngắn hoạt động nhờ package prefix mặc định. Cách viết đầy đủ nêu rõ package và vẫn hợp lệ khi không muốn dựa vào import prefix.

## 3. Ví dụ dùng String, Integer và Math

Có thể tận dụng các kiểu trong java.lang để gọi phương thức static hoặc đọc hằng số:

    T(String).valueOf(2026)

Biểu thức trả về chuỗi "2026".

    T(Integer).MAX_VALUE

Biểu thức trả về giá trị lớn nhất của kiểu int.

    T(Math).max(15, 28)

Biểu thức trả về số lớn hơn trong hai giá trị.

Có thể viết đầy đủ package để biểu đạt cùng ý định:

    T(java.lang.Math).max(15, 28)

Tên ngắn giúp biểu thức gọn hơn, nhất là khi xuất hiện nhiều lần trong cấu hình. Tên đầy đủ hữu ích trong tài liệu kỹ thuật, biểu thức có nhiều lớp cùng tên hoặc khi muốn người đọc nhận ra chính xác nguồn của kiểu được tham chiếu.

Lưu ý rằng T(Integer).MAX_VALUE đọc thành viên static của lớp Integer. Nó không phải là biến instance và cũng không tạo một đối tượng Integer mới.

## 4. Ví dụ đánh giá type reference bằng Java

Để dùng type reference, cần một EvaluationContext có TypeLocator hỗ trợ. Ví dụ sau sử dụng StandardEvaluationContext mặc định:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression =
            parser.parseExpression("T(String).valueOf(123)");

    String result = expression.getValue(context, String.class);

Trong ví dụ này:

1. StandardEvaluationContext cung cấp môi trường đánh giá biểu thức.
2. TypeLocator mặc định phân giải tên ngắn String thành java.lang.String.
3. Dấu chấm truy cập phương thức static valueOf.
4. getValue đánh giá biểu thức và chuyển kết quả về kiểu String được yêu cầu.

Kết quả là chuỗi "123".

Có thể đọc hằng số static theo cách tương tự:

    Expression maxExpression =
            parser.parseExpression("T(Integer).MAX_VALUE");

    Integer maxValue =
            maxExpression.getValue(context, Integer.class);

Nếu biểu thức cần một kiểu khác, có thể dùng tên đầy đủ của kiểu đó hoặc đăng ký package prefix phù hợp trong TypeLocator.

## 5. Package khác java.lang không được tự động import

Việc java.lang được đăng ký mặc định không có nghĩa mọi package trên classpath đều có thể dùng tên ngắn.

Ví dụ, biểu thức sau thường không phân giải được chỉ bằng tên lớp ngắn:

    T(LocalDate)

LocalDate thuộc package java.time, không thuộc java.lang. Có hai cách viết phù hợp:

    T(java.time.LocalDate)

hoặc đăng ký package prefix java.time cho TypeLocator:

    T(LocalDate)

Tương tự, BigDecimal thuộc java.math, nên có thể tham chiếu đầy đủ bằng:

    T(java.math.BigDecimal)

Không nên giả định rằng một package được import trong file Java của ứng dụng cũng tự động có hiệu lực trong SpEL. Java compiler và SpEL TypeLocator là hai cơ chế phân giải tên độc lập.

## 6. Đăng ký package prefix bằng StandardTypeLocator

Nếu nhiều biểu thức cần tham chiếu các kiểu trong cùng một package, có thể đăng ký package prefix một lần trong TypeLocator.

Ví dụ:

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.time");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

Sau khi đăng ký, biểu thức có thể dùng tên ngắn:

    T(LocalDate).of(2026, 11, 12)

Đối tượng StandardTypeLocator mặc định vẫn có package prefix java.lang. Việc đăng ký thêm java.time mở rộng danh sách package được tìm kiếm.

Nếu không còn cần một package prefix, có thể gỡ nó bằng:

    typeLocator.removeImport("java.time");

registerImport nhận tên package, không phải tên lớp riêng lẻ. Ví dụ, dùng java.time để phân giải LocalDate; không đăng ký java.time.LocalDate như một package.

Nếu có nhiều lớp trùng simple name ở các package khác nhau, nên dùng tên đầy đủ trong biểu thức để tránh phụ thuộc vào danh sách package prefix và thứ tự phân giải.

## 7. Ví dụ hoàn chỉnh với java.time.LocalDate

Có thể cấu hình TypeLocator để biểu thức dùng tên LocalDate ngắn gọn:

    ExpressionParser parser = new SpelExpressionParser();

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.time");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

    Expression expression =
            parser.parseExpression("T(LocalDate).of(2026, 11, 12)");

    LocalDate date =
            expression.getValue(context, LocalDate.class);

Biểu thức tham chiếu đến lớp LocalDate, sau đó gọi phương thức static of để tạo giá trị ngày. Đây là lời gọi static trên lớp; nó không phải thao tác tạo instance bằng toán tử new.

Nếu không muốn cấu hình package prefix, có thể viết trực tiếp:

    T(java.time.LocalDate).of(2026, 11, 12)

Cách đầy đủ này phù hợp với biểu thức đơn lẻ hoặc khi muốn giảm phụ thuộc vào cấu hình TypeLocator.

## 8. TypeLocator và class loader

TypeLocator không tự tạo ra hoặc cài đặt thư viện. Nó chỉ tìm một kiểu theo tên trong môi trường class loader mà nó sử dụng.

StandardTypeLocator có constructor mặc định và constructor nhận ClassLoader. Nếu ứng dụng chạy trong môi trường có class loader riêng, chẳng hạn ứng dụng server, plugin hoặc một số cách đóng gói ứng dụng, có thể cung cấp class loader phù hợp:

    StandardTypeLocator typeLocator =
            new StandardTypeLocator(
                    MyApplication.class.getClassLoader());

Sau đó có thể đăng ký package prefix như bình thường:

    typeLocator.registerImport("com.example.domain");

Điều này giúp TypeLocator tìm các lớp của ứng dụng theo class loader được chỉ định. Tuy nhiên, lớp vẫn phải có mặt trong runtime classpath/module path và có thể được class loader đó tải. Đăng ký package prefix không thay thế việc khai báo dependency hoặc đóng gói thư viện.

Nếu gặp lỗi không tìm thấy kiểu, hãy kiểm tra tên đầy đủ của lớp, package prefix đã đăng ký và class loader đang dùng. Không nên chỉ thêm package prefix liên tục khi lớp thực tế chưa có trong runtime.

## 9. StandardEvaluationContext và SimpleEvaluationContext

Không phải mọi EvaluationContext đều hỗ trợ type reference.

StandardEvaluationContext cung cấp bộ tính năng SpEL đầy đủ hơn và dùng StandardTypeLocator mặc định. Đây là lựa chọn phù hợp khi biểu thức cần T(...), truy cập thành viên static hoặc các tính năng nâng cao khác.

SimpleEvaluationContext được thiết kế cho tập tính năng giới hạn hơn, tập trung vào truy cập property và method theo cấu hình. Nó không hỗ trợ type references theo mặc định. Vì vậy, biểu thức:

    T(String).valueOf(123)

không phù hợp với một SimpleEvaluationContext chỉ đọc property thông thường.

Nếu biểu thức chỉ cần đọc dữ liệu từ root object, hãy ưu tiên context có quyền hạn hẹp hơn. Nếu thật sự cần type reference, dùng StandardEvaluationContext và giới hạn những khả năng khác theo nhu cầu ứng dụng.

## 10. Phân biệt type reference với biến và tên property

Tên kiểu, biến context và property của root object là ba loại tham chiếu khác nhau.

| Cách viết | Ý nghĩa |
|---|---|
| T(String) | Tham chiếu lớp java.lang.String |
| #name | Đọc biến name trong EvaluationContext |
| name | Đọc property name trên root object |
| T(Math).PI | Đọc thành viên static PI của Math |
| new String('hello') | Tạo instance String bằng constructor |

Nếu viết #String, SpEL sẽ tìm biến tên String chứ không tự hiểu đó là lớp String. Nếu viết String không có T(...), nó được hiểu như một property hoặc identifier trong ngữ cảnh biểu thức, không phải type reference.

Hãy dùng T(...) mỗi khi mục tiêu là tham chiếu một kiểu Java.

## 11. Lỗi thường gặp khi tham chiếu kiểu

| Biểu thức hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| T(LocalDate) không tìm thấy kiểu | java.time chưa được đăng ký | Dùng tên đầy đủ hoặc đăng ký java.time |
| T(String) lỗi với context giới hạn | Context không hỗ trợ type reference | Dùng StandardEvaluationContext khi cần T(...) |
| T(java.time.LocalDate) không tìm thấy lớp | Lớp không có trong runtime hoặc class loader không thấy | Kiểm tra dependency và class loader |
| Dùng #String để tham chiếu lớp | # biểu thị biến context | Dùng T(String) |
| Dùng T(String) khi muốn tạo đối tượng | T chỉ tham chiếu lớp | Dùng new với constructor phù hợp |
| Hai package có lớp cùng tên ngắn | Tên ngắn có thể phân giải sang kiểu không mong muốn | Dùng tên package đầy đủ |

Khi phân tích lỗi, cần phân biệt lỗi parse cú pháp với lỗi phân giải kiểu lúc đánh giá. Biểu thức có thể đúng cú pháp nhưng TypeLocator không tìm thấy lớp. Khi đó, kiểm tra package và class loader sẽ hữu ích hơn việc thay đổi các toán tử khác trong biểu thức.

## 12. Giới hạn bảo mật khi dùng type reference

Type reference có thể mở rộng những gì biểu thức làm được. Sau khi phân giải một lớp, biểu thức có thể đọc thành viên static hoặc gọi phương thức static mà context cho phép. Vì vậy, không nên lấy biểu thức tùy ý từ người dùng bên ngoài rồi đánh giá bằng StandardEvaluationContext có quyền rộng.

Một số nguyên tắc vận hành:

- Chỉ đánh giá biểu thức từ nguồn đáng tin cậy hoặc đã được quản trị.
- Chỉ đăng ký những package prefix mà rule thực sự cần.
- Dùng tên đầy đủ và allowlist kiểu khi có thể để giới hạn lớp được phép tham chiếu.
- Không đưa bean hoặc object có quyền cao vào context nếu biểu thức không cần.
- Hạn chế method resolver và property accessor theo đúng phạm vi sử dụng.
- Kiểm thử biểu thức và xử lý lỗi phân giải kiểu trước khi đưa rule vào luồng nghiệp vụ quan trọng.

Nếu không cần type reference, hãy dùng SimpleEvaluationContext với tập tính năng nhỏ hơn. Nếu cần T(...), hãy cấu hình StandardEvaluationContext có chủ đích, thay vì coi mọi biểu thức SpEL là chuỗi văn bản vô hại.

## 13. Khi nào nên dùng tên ngắn và khi nào nên dùng tên đầy đủ?

Tên ngắn phù hợp khi kiểu thuộc package java.lang đã được đăng ký mặc định hoặc khi ứng dụng chủ động đăng ký một package prefix và nhóm biểu thức dùng thống nhất cấu hình đó.

Ví dụ:

    T(String)
    T(Integer)
    T(LocalDate)

Tên đầy đủ phù hợp khi:

- Biểu thức chỉ xuất hiện một lần và không cần thêm cấu hình package.
- Có nhiều lớp trùng tên ở các package khác nhau.
- Muốn biểu thức tự mô tả package mà không phụ thuộc cấu hình TypeLocator.
- Rule được chuyển giữa các ứng dụng có danh sách package prefix khác nhau.

Ví dụ:

    T(java.lang.String)
    T(java.time.LocalDate)
    T(java.math.BigDecimal)

Dùng tên ngắn giúp giảm độ dài; dùng tên đầy đủ giúp giảm sự mơ hồ. Hãy ưu tiên tính rõ ràng của rule và tính ổn định của cấu hình.

## Kết luận

Với StandardEvaluationContext và StandardTypeLocator mặc định, package java.lang đã được đăng ký nên các kiểu như String, Integer và Math có thể được tham chiếu bằng T(String), T(Integer) và T(Math). Các package khác không tự động được import; hãy dùng tên đầy đủ hoặc đăng ký package prefix bằng StandardTypeLocator.registerImport().

T(...) trả về tham chiếu đến lớp, cho phép truy cập thành viên static và dùng trong các biểu thức như instanceof. Nó không tạo instance; việc tạo đối tượng dùng cú pháp new. SimpleEvaluationContext không hỗ trợ type reference theo mặc định, nên cần chọn context phù hợp. Vì type reference có thể mở ra quyền truy cập thành viên của lớp, chỉ nên đánh giá biểu thức từ nguồn đáng tin cậy và giới hạn các kiểu được phép tham chiếu.