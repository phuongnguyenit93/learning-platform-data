# Cú pháp gọi function bằng #functionName

## Mục tiêu

Spring Expression Language (SpEL) cho phép ứng dụng đăng ký một Java method như một function trong EvaluationContext, sau đó gọi function đó từ expression bằng cú pháp **#functionName(arguments)**. Cách này giúp đưa một phép tính hoặc quy tắc dùng chung vào biểu thức mà không phải viết lại logic ở nhiều nơi.

Function trong SpEL thường được triển khai bằng một public static method. Ứng dụng lấy đối tượng Method bằng reflection, đăng ký method dưới một tên dễ đọc, rồi expression gọi tên đó với các đối số cần thiết.

Sau bài này, bạn có thể:

- Hiểu cú pháp gọi function bằng #functionName.
- Đăng ký một public static method bằng StandardEvaluationContext.
- Truyền literal, biến và property làm đối số.
- Dùng giá trị trả về của function trong điều kiện và collection operation.
- Phân biệt function với biến, property và instance method.
- Kiểm tra kiểu đối số, kiểu trả về và lỗi khi thực thi.
- Giới hạn các function được phép gọi từ expression.

## 1. Cú pháp gọi function

Cú pháp tổng quát:

~~~text
#functionName(argument1, argument2, ...)
~~~

Dấu # cho SpEL biết đây là tên function được đăng ký trong EvaluationContext. Tên function trong phần đăng ký không có dấu #; dấu này chỉ xuất hiện khi tham chiếu trong expression.

Ví dụ:

~~~text
#normalizeCode(' ab-123 ')
#isEligible(#customer, 18)
#calculateTax(#amount, #taxRate)
~~~

Các đối số có thể là literal, biến, property của root object, kết quả của một expression khác hoặc kết quả từ function khác. Nếu function không nhận đối số, vẫn phải viết cặp ngoặc:

~~~text
#currentTimestamp()
~~~

Function trả về một giá trị. Giá trị đó có thể được dùng như một phần của expression lớn hơn, chẳng hạn so sánh, truy cập property hoặc truyền vào một function khác.

## 2. Function là Java method được đăng ký

Một function SpEL thường tham chiếu tới một public static method. Ví dụ, tạo lớp tiện ích:

~~~java
package com.example.spel;

public class TextFunctions {

    public static String normalizeCode(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toUpperCase();
    }
}
~~~

Method normalizeCode nhận một String và trả về String đã loại khoảng trắng ở hai đầu, chuyển thành chữ hoa.

Ứng dụng cần lấy đối tượng java.lang.reflect.Method đại diện cho method này rồi đăng ký nó trong EvaluationContext.

~~~java
Method normalizeMethod = TextFunctions.class.getMethod(
    "normalizeCode",
    String.class
);
~~~

getMethod tìm public method theo tên và kiểu tham số. Nếu method không tồn tại hoặc chữ ký không khớp, Java sẽ ném NoSuchMethodException khi tạo cấu hình; nên phát hiện lỗi này khi khởi tạo ứng dụng thay vì đợi tới lúc expression chạy.

## 3. Đăng ký function trong StandardEvaluationContext

Ví dụ hoàn chỉnh:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

Method normalizeMethod = TextFunctions.class.getMethod(
    "normalizeCode",
    String.class
);

context.registerFunction("normalizeCode", normalizeMethod);

Expression expression =
    parser.parseExpression("#normalizeCode(' ab-123 ')");

String result = expression.getValue(context, String.class);
~~~

Kết quả là:

~~~text
AB-123
~~~

Các bước chính:

1. Tạo hoặc lấy một StandardEvaluationContext.
2. Lấy Method của public static method cần công bố.
3. Gọi registerFunction với tên function và Method.
4. Parse expression có tham chiếu #normalizeCode(...).
5. Đánh giá expression trong chính context đã đăng ký function.

Tên truyền cho registerFunction là normalizeCode, không có dấu #. Trong expression phải viết #normalizeCode(...). Nếu function chưa được đăng ký trong context dùng để đánh giá, SpEL không thể phân giải lời gọi đó.

Có thể đăng ký nhiều function trên cùng một context:

~~~java
context.registerFunction("normalizeCode", normalizeMethod);
context.registerFunction("isValidCode", isValidCodeMethod);
context.registerFunction("calculateTax", calculateTaxMethod);
~~~

Chỉ đăng ký những function mà expression thực sự cần.

## 4. Truyền đối số vào function

Function có thể nhận một hoặc nhiều đối số. Số lượng và kiểu đối số phải phù hợp với chữ ký Java method đã đăng ký.

Ví dụ:

~~~java
public class PricingFunctions {

    public static BigDecimal calculateTax(
            BigDecimal amount,
            BigDecimal taxRate) {
        return amount.multiply(taxRate);
    }
}
~~~

Đăng ký function:

~~~java
Method calculateTaxMethod = PricingFunctions.class.getMethod(
    "calculateTax",
    BigDecimal.class,
    BigDecimal.class
);

context.registerFunction("calculateTax", calculateTaxMethod);
context.setVariable("amount", new BigDecimal("200.00"));
context.setVariable("taxRate", new BigDecimal("0.10"));
~~~

Gọi function:

~~~text
#calculateTax(#amount, #taxRate)
~~~

Kết quả là BigDecimal có giá trị 20.00.

Đối số cũng có thể là property của root object:

~~~text
#calculateTax(#root.subtotal, #root.taxRate)
~~~

Hoặc kết hợp literal với biến:

~~~text
#calculateTax(#root.subtotal, 0.10)
~~~

Trong ứng dụng tài chính, nên dùng BigDecimal nhất quán cho amount và rate. Tránh truyền số floating point rồi phụ thuộc vào chuyển đổi ngầm nếu độ chính xác thập phân có ý nghĩa.

### Kiểu đối số và chuyển đổi

SpEL có cơ chế chuyển đổi kiểu thông qua TypeConverter của EvaluationContext trong các tình huống được hỗ trợ. Dù vậy, nên truyền đối số có kiểu tương thích với method đã đăng ký. Đặc biệt với overload hoặc kiểu số, hãy kiểm thử các giá trị thực tế để tránh chọn sai kiểu hoặc gặp lỗi chuyển đổi khi chạy.

Một function được đăng ký bằng một Method cụ thể. Nếu cần hành vi khác với chữ ký đó, hãy đăng ký một function khác với tên rõ ràng hoặc viết một method Java trung gian có chữ ký ổn định.

## 5. Dùng giá trị trả về của function

Kết quả function là một giá trị SpEL thông thường. Có thể so sánh kết quả:

~~~text
#isValidCode(#root.code) == true
~~~

Dùng trong điều kiện:

~~~text
#isEligible(#root.customer, #minimumAge) and #root.account.active
~~~

Hoặc truyền kết quả vào function khác:

~~~text
#formatLabel(#normalizeCode(#root.code))
~~~

Nếu function trả về object, expression có thể tiếp tục đọc property hoặc gọi thao tác được context hỗ trợ trên object đó:

~~~text
#parseCustomer(#root.rawCustomer).status
~~~

Kiểu trả về cần phù hợp với cách sử dụng tiếp theo. Nếu method trả về null, expression phía sau phải xử lý null đúng cách. Safe navigation có thể bảo vệ việc truy cập trên một kết quả null:

~~~text
#parseCustomer(#root.rawCustomer)?.status
~~~

Safe navigation không xử lý lỗi bên trong function. Nếu method ném exception, quá trình đánh giá vẫn thất bại.

## 6. Dùng function trong collection selection

Function có thể đóng gói một điều kiện dùng chung và được gọi cho từng phần tử trong collection.

Ví dụ Java:

~~~java
public class CustomerFunctions {

    public static boolean isEligible(Customer customer, int minimumAge) {
        return customer != null
            && customer.getAge() >= minimumAge
            && customer.isActive();
    }
}
~~~

Đăng ký:

~~~java
Method eligibleMethod = CustomerFunctions.class.getMethod(
    "isEligible",
    Customer.class,
    int.class
);

context.registerFunction("isEligible", eligibleMethod);
context.setVariable("minimumAge", 18);
~~~

Selection:

~~~text
#root.customers.?[#isEligible(#this, #minimumAge)]
~~~

Trong selection, #this là Customer hiện tại. #minimumAge là biến được ứng dụng truyền vào context. Function trả về Boolean để quyết định phần tử có được giữ lại hay không.

Có thể dùng function trong projection:

~~~text
#root.customers.![#normalizeCode(#this.code)]
~~~

Kết quả là danh sách mã đã được chuẩn hóa. Hãy tránh function có side effect trong selection hoặc projection vì SpEL có thể gọi function nhiều lần, một lần cho mỗi phần tử.

## 7. Phân biệt function với biến, property và method

Các cú pháp sau có ý nghĩa khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| **#normalizeCode('ab')** | Gọi function đã đăng ký trong EvaluationContext |
| **#minimumAge** | Đọc biến minimumAge trong EvaluationContext |
| **#root.name** | Đọc property name của root object |
| **#this.name** | Đọc property name của object hiện tại |
| **#root.normalizeCode()** | Gọi instance method trên root object, nếu context cho phép |

Function được đăng ký theo tên và được gọi bằng #functionName(...). Instance method được gọi trên một object cụ thể bằng cú pháp object.method(...). Hai cơ chế này không thay thế nhau.

Function cũng không tự động là Spring bean. Việc đăng ký một static Method không làm class chứa method trở thành bean, và không kích hoạt dependency injection cho method đó.

Nếu logic cần service, repository hoặc client được Spring quản lý, đừng cố biến static function thành nơi giữ dependency. Hãy thực hiện logic trong service Java hoặc dùng một cơ chế bean reference được cấu hình và kiểm soát phù hợp.

## 8. Function và vòng đời EvaluationContext

Function được đăng ký trên EvaluationContext. Khi ứng dụng tạo context mới, cần đăng ký lại các function cần dùng trong context đó hoặc dùng một factory chung để xây dựng context.

Ví dụ factory đơn giản:

~~~java
public class SpelContextFactory {

    public StandardEvaluationContext create(Object rootObject)
            throws NoSuchMethodException {

        StandardEvaluationContext context =
            new StandardEvaluationContext(rootObject);

        Method normalizeMethod = TextFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

        context.registerFunction("normalizeCode", normalizeMethod);

        return context;
    }
}
~~~

Cách tạo context tập trung giúp tránh việc một luồng đánh giá có function còn luồng khác lại thiếu function.

Expression có thể được parse một lần và tái sử dụng. Tuy nhiên, context chứa root object, biến và function registrations cần có vòng đời phù hợp với dữ liệu và tính đồng thời của ứng dụng.

Không chia sẻ context mutable giữa nhiều request nếu các request có thể thay đổi biến hoặc root object của nhau. Hãy tạo context riêng theo request hoặc dùng một cấu hình bất biến phù hợp.

## 9. Xử lý null và exception

Function phải định nghĩa rõ cách xử lý đối số null. Có hai lựa chọn thường gặp:

- Chấp nhận null và trả về giá trị được quy định, ví dụ normalizeCode(null) trả về null.
- Từ chối null bằng cách ném exception có thông báo rõ ràng nếu đầu vào bắt buộc.

Không để hành vi null phụ thuộc vào lỗi ngẫu nhiên như NullPointerException nếu có thể xác định hợp đồng ngay trong method.

Nếu function ném exception trong lúc đánh giá, SpEL báo lỗi đánh giá và exception gốc có thể nằm trong cause chain. Khi xử lý lỗi:

- Xác định function nào được gọi.
- Kiểm tra số lượng và kiểu đối số.
- Kiểm tra giá trị null và dữ liệu biên.
- Xem exception gốc từ Java method.
- Không biến mọi lỗi thành null nếu null không phải kết quả nghiệp vụ hợp lệ.

Có thể bọc lỗi ở ranh giới ứng dụng để cung cấp thông báo nghiệp vụ ổn định, đồng thời giữ nguyên cause để chẩn đoán.

## 10. Giới hạn và an toàn khi công bố function

Function mở một Java method cho expression. Vì vậy, việc đăng ký function là một quyết định về khả năng mà expression được phép thực hiện.

Các nguyên tắc:

- Chỉ đăng ký method có mục đích rõ và cần thiết cho biểu thức.
- Ưu tiên function thuần: nhận đầu vào, trả kết quả và không thay đổi trạng thái bên ngoài.
- Tránh công bố method ghi database, gửi email, mở kết nối hoặc thực hiện I/O nếu expression chỉ cần tính toán.
- Không đăng ký method có thể truy cập file, process, credential hoặc tài nguyên ngoài phạm vi nghiệp vụ.
- Kiểm tra kiểu và miền giá trị của đối số trong Java method.
- Không đưa dữ liệu nhạy cảm vào kết quả function hoặc log không cần thiết.
- Kiểm soát nguồn expression; người dùng có thể gọi các function đã được công bố nếu họ có thể viết expression.
- Dùng EvaluationContext với phạm vi quyền tối thiểu cần thiết.

Tên function không phải cơ chế phân quyền. Nếu người dùng được phép gọi một function, method đó cần tự bảo đảm rằng đầu vào và thao tác đều được phép theo nghiệp vụ.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không phân giải được function | Function chưa được đăng ký trong context đang dùng hoặc sai tên | Kiểm tra registerFunction và tên #functionName |
| Lỗi khi lấy Method | Sai tên method hoặc chữ ký tham số | Kiểm tra class, method và kiểu tham số trong getMethod |
| Function không được gọi | Thiếu dấu #, thiếu ngoặc hoặc dùng nhầm cú pháp instance method | Kiểm tra #name(arguments) |
| Sai số lượng đối số | Expression truyền số đối số khác chữ ký Method | Đối chiếu lời gọi và khai báo Java |
| Lỗi kiểu đối số | Kiểu thực tế không tương thích hoặc conversion không phù hợp | Chuẩn hóa kiểu trước khi gọi và kiểm thử TypeConverter |
| Function trả null ngoài dự kiến | Đối số null hoặc logic method có nhánh trả null | Xác định hợp đồng null và kiểm tra đầu vào |
| Lỗi khi truy cập kết quả | Function trả null hoặc kiểu trả về khác dự kiến | Kiểm tra kiểu trả về và dùng safe navigation khi phù hợp |
| Hoạt động ở context này nhưng không ở context khác | Context thứ hai chưa đăng ký function | Dùng chung context factory |
| Kết quả không ổn định | Function có side effect hoặc phụ thuộc trạng thái thay đổi | Làm function thuần hoặc quản lý trạng thái ngoài expression |

Khi chẩn đoán, tách lỗi cấu hình Method khỏi lỗi parse expression và lỗi runtime bên trong function. Việc lấy Method nên được kiểm tra khi khởi tạo ứng dụng; việc đánh giá expression cần được kiểm thử với dữ liệu đại diện.

## 12. Kiểm thử function

Kiểm thử nên xác nhận method được đăng ký, expression gọi đúng function và kết quả có kiểu mong đợi.

Ví dụ:

~~~java
@Test
void callsRegisteredFunction() throws Exception {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Method method = TextFunctions.class.getMethod(
        "normalizeCode",
        String.class
    );

    context.registerFunction("normalizeCode", method);

    Expression expression =
        parser.parseExpression("#normalizeCode(' ab-123 ')");

    assertEquals("AB-123", expression.getValue(context, String.class));
}
~~~

Nên có các trường hợp:

- Function được đăng ký đúng tên.
- Function chưa đăng ký.
- Tên function sai.
- Số lượng đối số đúng và sai.
- Kiểu đối số đúng và không tương thích.
- Đối số null.
- Giá trị biên và dữ liệu không hợp lệ.
- Function trả về null.
- Function trả về Boolean, số, String hoặc object.
- Function được gọi trong selection/projection.
- Context mới được tạo qua factory vẫn có đủ function.
- Function không tạo side effect ngoài dự kiến.

Nếu function dùng reflection để lấy Method, kiểm tra lỗi cấu hình ngay khi khởi động và làm cho ứng dụng không kích hoạt expression phụ thuộc vào function bị thiếu.

## 13. Quy trình thêm một function mới

Khi cần cung cấp một phép xử lý cho SpEL:

1. **Xác định mục đích.** Chọn một phép tính hoặc quy tắc nhỏ mà expression thực sự cần.
2. **Viết public static method.** Khai báo kiểu đối số, kiểu trả về và hành vi null rõ ràng.
3. **Kiểm tra side effect.** Đảm bảo method không thay đổi trạng thái hoặc thực hiện thao tác ngoài ý muốn.
4. **Lấy Method bằng reflection.** Dùng tên và danh sách kiểu tham số chính xác.
5. **Đăng ký vào context.** Dùng tên ngắn, ổn định và không có dấu # trong registerFunction.
6. **Gọi trong expression.** Dùng cú pháp #functionName(arguments).
7. **Kiểm thử.** Bao phủ kiểu đối số, giá trị null, kết quả và lỗi runtime.
8. **Kiểm soát quyền.** Chỉ cung cấp function cho expression và nguồn người dùng được phép gọi nó.

Nếu function bắt đầu cần nhiều dependency hoặc có nhiều bước nghiệp vụ, hãy chuyển logic sang một service Java được Spring quản lý. SpEL nên diễn đạt điều kiện hoặc kết hợp kết quả, không trở thành nơi điều phối toàn bộ ứng dụng.

## 14. Thực hành tốt

- Đăng ký public static method bằng registerFunction(name, method).
- Dùng tên không có dấu # khi đăng ký và dùng #name(...) khi gọi.
- Giữ function nhỏ, có tên mô tả hành vi và chữ ký ổn định.
- Dùng kiểu Java cụ thể cho đối số và giá trị trả về.
- Kiểm tra null và dữ liệu biên ngay trong function.
- Tái sử dụng Expression nhưng quản lý EvaluationContext theo vòng đời dữ liệu.
- Dùng một context factory để đăng ký function nhất quán.
- Dùng function thuần trong selection/projection để tránh side effect khi được gọi nhiều lần.
- Không dùng function static để thay thế service có dependency injection.
- Chỉ công bố các function cần thiết và kiểm soát nguồn expression.
- Kiểm thử cả cấu hình reflection lẫn hành vi runtime.
- Chuyển logic nghiệp vụ nhiều bước sang Java khi expression trở nên khó đọc.

## 15. Checklist review

Trước khi chấp nhận expression gọi function, hãy kiểm tra:

- [ ] Function có tên và mục đích rõ ràng.
- [ ] Java method là public static và có chữ ký phù hợp.
- [ ] Method được lấy bằng reflection với đúng kiểu tham số.
- [ ] Function được đăng ký trong đúng EvaluationContext.
- [ ] Tên đăng ký không có dấu #; expression gọi bằng #functionName(...).
- [ ] Số lượng và kiểu đối số phù hợp.
- [ ] Kiểu trả về được dùng đúng trong expression.
- [ ] Null và exception có hợp đồng rõ ràng.
- [ ] Function không có side effect không mong muốn.
- [ ] Function không được dùng để thay thế dependency injection.
- [ ] Context factory đăng ký function nhất quán giữa test và production.
- [ ] Nguồn expression và tập function được công bố được kiểm soát.

## Kết luận

SpEL gọi function bằng cú pháp **#functionName(arguments)** sau khi ứng dụng đăng ký một Java Method trong EvaluationContext. Cách thông dụng là dùng public static method, lấy Method bằng reflection rồi gọi registerFunction trên StandardEvaluationContext. Function có thể nhận biến, property và giá trị literal; kết quả của nó tiếp tục được dùng trong điều kiện, selection hoặc projection. Hãy giữ function nhỏ, có kiểu dữ liệu và hành vi null rõ ràng, tránh side effect, đăng ký nhất quán trong từng context và chỉ công bố những thao tác mà expression được phép thực hiện.