# Tham chiếu kiểu đầy đủ package trong SpEL

## Mục tiêu

Spring Expression Language (SpEL) cho phép tham chiếu một kiểu Java bằng toán tử **T(...)**. Sau khi phân giải được kiểu, biểu thức có thể truy cập thành viên static như hằng số, enum constant hoặc gọi static method. Với các kiểu nằm ngoài package java.lang, cách viết đầy đủ package giúp SpEL xác định đúng class mà không phụ thuộc vào import prefix ngắn.

Bài này tập trung vào cú pháp tham chiếu kiểu có tên package đầy đủ, cơ chế phân giải kiểu và cách sử dụng an toàn trong EvaluationContext.

Sau bài này, bạn có thể:

- Viết type reference bằng cú pháp T(fully.qualified.ClassName).
- Phân biệt tên kiểu đầy đủ package với tên kiểu được import.
- Truy cập static field, static method và enum constant.
- Dùng type reference trong biểu thức kiểm tra kiểu.
- Hiểu vai trò của TypeLocator và class loader.
- Nhận diện giới hạn của SimpleEvaluationContext và rủi ro khi đánh giá biểu thức không đáng tin cậy.

## 1. Cú pháp type reference

Cú pháp tham chiếu kiểu:

~~~text
T(fully.qualified.ClassName)
~~~

Ví dụ:

~~~text
T(java.lang.String)
T(java.util.Locale)
T(java.time.LocalDate)
T(java.math.BigDecimal)
~~~

Phần bên trong ngoặc là tên class mà SpEL cần phân giải. Với tên đầy đủ package, tên được viết từ package gốc tới class, ví dụ java.time.LocalDate.

Toán tử T(...) trả về đối tượng Class tương ứng với kiểu đã phân giải. Từ đối tượng Class này, biểu thức có thể truy cập thành viên static hoặc dùng kiểu trong các phép kiểm tra mà SpEL hỗ trợ.

Tên đầy đủ package đặc biệt hữu ích khi kiểu không thuộc java.lang. SpEL mặc định có import prefix java.lang, vì vậy một số kiểu phổ biến như String có thể được viết ngắn:

~~~text
T(String)
~~~

Cả hai cách sau đều tham chiếu cùng kiểu:

~~~text
T(String)
T(java.lang.String)
~~~

Khi viết tài liệu, cấu hình hoặc biểu thức được lưu lâu dài, tên đầy đủ package giúp người đọc nhận ra chính xác class được dùng và giảm phụ thuộc vào import prefix của TypeLocator.

## 2. Truy cập static field và hằng số

Sau khi tham chiếu kiểu, có thể dùng dấu chấm để đọc static field:

~~~text
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
T(java.math.BigDecimal).ZERO
~~~

Ví dụ, biểu thức sau trả về hằng số PI:

~~~text
T(java.lang.Math).PI
~~~

Một số tình huống sử dụng:

- Lấy giới hạn số nguyên từ Integer.MAX_VALUE.
- Dùng BigDecimal.ZERO làm giá trị số thập phân ban đầu.
- Đọc hằng số do class nghiệp vụ định nghĩa.
- Dùng enum constant làm giá trị cấu hình.

Static field được truy cập theo tên thành viên của class. Tên class cần được phân giải trước; nếu package hoặc class sai, SpEL không thể tiếp tục đọc field.

### Enum constant

Enum constant cũng là thành viên static của kiểu enum:

~~~text
T(java.time.DayOfWeek).MONDAY
T(java.math.RoundingMode).HALF_UP
~~~

Ví dụ, có thể truyền enum constant vào một biểu thức so sánh:

~~~text
#roundingMode == T(java.math.RoundingMode).HALF_UP
~~~

Biểu thức này so sánh biến roundingMode với hằng enum HALF_UP. Biến phải được cung cấp trong EvaluationContext và có kiểu phù hợp.

## 3. Gọi static method

Có thể gọi static method bằng cách đặt tên method sau type reference:

~~~text
T(java.lang.Math).max(10, 20)
T(java.util.UUID).fromString(#id)
T(java.time.LocalDate).parse('2026-11-12')
~~~

Ví dụ:

~~~text
T(java.lang.Math).max(10, 20)
~~~

Kết quả là 20.

Một ví dụ khác dùng BigDecimal:

~~~text
T(java.math.BigDecimal).valueOf(125)
~~~

Biểu thức gọi static method valueOf trên BigDecimal và trả về một BigDecimal.

Với method có nhiều overload, SpEL cần phân giải method dựa trên tên và kiểu đối số. Hãy truyền đối số có kiểu rõ ràng và kiểm thử những trường hợp có thể gây nhập nhằng giữa các overload.

Type reference không tự chuyển một instance method thành static method. Cú pháp T(...) tham chiếu class; lời gọi sau dấu chấm phải phù hợp với thành viên static mà class cung cấp.

## 4. Dùng type reference trong phép kiểm tra kiểu

Type reference có thể xuất hiện trong toán tử instanceof:

~~~text
#value instanceof T(java.lang.String)
~~~

Biểu thức trả về true nếu value là một String hoặc một instance tương thích theo quy tắc instanceof của Java.

Ví dụ kiểm tra một biến có phải BigDecimal:

~~~text
#amount instanceof T(java.math.BigDecimal)
~~~

Điều này hữu ích khi một biến hoặc property có thể nhận nhiều kiểu dữ liệu và biểu thức cần chọn nhánh xử lý phù hợp.

Có thể kết hợp với toán tử logic:

~~~text
#amount != null and #amount instanceof T(java.math.BigDecimal)
~~~

Điều kiện null đứng trước giúp biểu thức thể hiện rõ rằng chỉ kiểm tra kiểu khi có giá trị.

Không dùng instanceof để thay thế hợp đồng kiểu của ứng dụng. Nếu property luôn phải là BigDecimal, nên xác định kiểu ở model và kiểm tra tại ranh giới dữ liệu thay vì dựa vào một biểu thức runtime ở mọi nơi.

## 5. Tên đầy đủ package và import prefix

SpEL sử dụng TypeLocator để phân giải tên kiểu. StandardTypeLocator là triển khai mặc định thường được dùng cùng StandardEvaluationContext.

StandardTypeLocator có import prefix mặc định cho java.lang. Vì vậy:

~~~text
T(String)
T(Integer)
T(Math)
~~~

có thể được phân giải mà không cần viết java.lang.

Với class ngoài java.lang, có thể viết tên đầy đủ package:

~~~text
T(java.time.LocalDate)
T(java.util.UUID)
T(java.math.BigDecimal)
~~~

Hoặc đăng ký package import prefix vào StandardTypeLocator rồi dùng tên class ngắn hơn. Ví dụ:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("java.time");

context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký java.time, biểu thức có thể dùng:

~~~text
T(LocalDate).parse('2026-11-12')
~~~

Import prefix chỉ giúp rút gọn tên class. Nó không thay đổi bản chất của type reference và không biến class thành một kiểu được phép an toàn trong mọi biểu thức.

### Khi nào nên dùng tên đầy đủ package?

Dùng tên đầy đủ package khi:

- Biểu thức được lưu trong database hoặc file cấu hình và cần tự mô tả.
- Có nhiều class cùng tên ở các package khác nhau.
- Không muốn phụ thuộc vào import prefix do một context cụ thể đăng ký.
- Muốn người review nhìn thấy chính xác class được tham chiếu.
- Biểu thức được chia sẻ giữa nhiều ứng dụng có cấu hình TypeLocator khác nhau.

Dùng tên ngắn khi ứng dụng có một quy ước import prefix rõ ràng và được kiểm soát tập trung. Nếu có hai class cùng tên trong các package đã import, tên đầy đủ package loại bỏ sự nhập nhằng.

## 6. Cấu hình TypeLocator

TypeLocator chịu trách nhiệm tìm class theo tên mà biểu thức cung cấp. StandardEvaluationContext cho phép thay TypeLocator:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator locator = new StandardTypeLocator();
context.setTypeLocator(locator);
~~~

Nếu cần thêm package prefix:

~~~java
locator.registerImport("java.time");
locator.registerImport("java.math");
~~~

Khi đó, tên class ngắn có thể được tìm trong các package đã đăng ký.

Có thể cấu hình TypeLocator dùng class loader phù hợp với môi trường ứng dụng, chẳng hạn khi chạy trong container, plugin system hoặc môi trường có nhiều class loader. Điều này quan trọng vì class có thể tồn tại trong ứng dụng nhưng không nhìn thấy từ class loader mà TypeLocator đang sử dụng.

Khi type reference hoạt động ở máy phát triển nhưng không hoạt động trong production, hãy kiểm tra:

- Class có thực sự nằm trên runtime classpath không.
- Package và tên class có chính xác không.
- Class loader đang được TypeLocator sử dụng.
- TypeLocator có import prefix cần thiết không.
- Ứng dụng có thay EvaluationContext hoặc TypeLocator giữa các môi trường không.

Không nên sửa lỗi bằng cách thêm hàng loạt package import mà chưa xác định class nào cần thiết. Hãy cấu hình rõ những package mà biểu thức được phép tham chiếu.

## 7. Kết hợp type reference với property, biến và biểu thức khác

Type reference có thể xuất hiện trong một biểu thức lớn hơn. Ví dụ, so sánh một biến enum với hằng enum:

~~~text
#status == T(com.example.OrderStatus).APPROVED
~~~

Hoặc dùng static method để tính giá trị:

~~~text
T(java.lang.Math).max(#minimum, #requested)
~~~

Có thể sử dụng kết quả trong điều kiện:

~~~text
#amount >= T(java.math.BigDecimal).ZERO
~~~

Ví dụ này kiểm tra amount không âm. Biến amount phải là kiểu tương thích với phép so sánh BigDecimal; không nên trộn kiểu số tùy ý mà không xác định conversion.

Type reference cũng có thể được dùng trong collection operation:

~~~text
#root.values.?[#this instanceof T(java.lang.String)]
~~~

Biểu thức giữ lại những phần tử có kiểu String. Trong selection, #this là phần tử hiện tại; type reference chỉ xác định class dùng trong phép kiểm tra kiểu.

Giữ biểu thức dễ đọc bằng cách tránh nhồi quá nhiều static call và điều kiện kiểu vào một dòng. Nếu logic yêu cầu nhiều phép chuyển đổi hoặc nhiều nhánh, hãy chuyển phần tính toán vào method Java có tên rõ ràng.

## 8. Giới hạn theo EvaluationContext

Không phải EvaluationContext nào cũng hỗ trợ type reference.

StandardEvaluationContext cung cấp phạm vi chức năng rộng hơn và hỗ trợ type resolution thông qua TypeLocator. Trong khi đó, SimpleEvaluationContext được thiết kế cho tập thao tác giới hạn hơn và không hỗ trợ type references, constructors hoặc bean references.

Ví dụ context dùng cho type reference:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
ExpressionParser parser = new SpelExpressionParser();

Object result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context);
~~~

Nếu biểu thức chạy trong SimpleEvaluationContext, không nên giả định rằng T(...) sẽ hoạt động chỉ vì property access hoặc một số instance method đang hoạt động. Hãy chọn context phù hợp với chức năng biểu thức cần dùng.

Khi ứng dụng xây dựng EvaluationContext qua factory, hãy dùng cùng factory trong kiểm thử và production. Điều này giúp tránh tình trạng biểu thức được xác nhận trong context rộng nhưng lại chạy trong context bị giới hạn hơn.

## 9. An toàn khi đánh giá type reference

Type reference có thể mở ra khả năng truy cập static method và static field của class mà TypeLocator phân giải được. Nếu biểu thức đến từ người dùng hoặc nguồn không đáng tin cậy, khả năng này có thể vượt quá quyền mà ứng dụng dự định cấp.

Ví dụ, một biểu thức có thể gọi static method trên một class ngoài phạm vi nghiệp vụ. Việc chỉ yêu cầu tên class đầy đủ package không làm biểu thức trở nên an toàn; nó chỉ làm tên class rõ ràng hơn.

Các nguyên tắc kiểm soát:

- Chỉ đánh giá biểu thức từ nguồn được tin cậy hoặc đã qua bước kiểm duyệt.
- Dùng EvaluationContext với phạm vi khả năng tối thiểu cần thiết.
- Cấu hình TypeLocator có kiểm soát, chỉ cho phép các package hoặc class ứng dụng cần.
- Tránh cung cấp StandardEvaluationContext rộng cho biểu thức do người dùng tùy ý nhập.
- Không để biểu thức gọi static method có tác dụng phụ nếu nghiệp vụ chỉ cần tính toán.
- Giới hạn quyền truy cập vào bean, method, constructor và type theo thiết kế của ứng dụng.
- Ghi nhận ID và phiên bản biểu thức khi có lỗi để truy vết.

TypeLocator không phải một sandbox hoàn chỉnh. Việc giới hạn tên class cần đi cùng với kiểm soát method resolution, property access, bean resolution và nguồn biểu thức.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy class | Sai package, sai tên class hoặc class không có trên runtime classpath | Kiểm tra fully qualified name và dependency |
| Tên ngắn không được phân giải | Package chưa được đăng ký trong TypeLocator | Dùng tên đầy đủ package hoặc đăng ký import prefix |
| Tên class bị nhập nhằng | Có nhiều class cùng tên trong các package đã import | Dùng tên đầy đủ package |
| Không gọi được static method | Method không tồn tại, không phù hợp chữ ký hoặc không phải static | Kiểm tra class, tên method và kiểu đối số |
| Không đọc được static field | Field không tồn tại hoặc không thể truy cập | Kiểm tra tên thành viên và visibility |
| Type reference thất bại trong context | Context không hỗ trợ type references | Dùng StandardEvaluationContext khi phù hợp |
| Class tồn tại nhưng không tìm thấy ở production | Class loader hoặc runtime dependency khác nhau | Kiểm tra TypeLocator và class loader |
| Biểu thức không an toàn | Nguồn biểu thức có thể gọi class ngoài phạm vi | Giới hạn TypeLocator và quyền của EvaluationContext |

Khi chẩn đoán, tách lỗi parse khỏi lỗi type resolution. Chuỗi T(...) có thể đúng cú pháp nhưng class vẫn không được tìm thấy khi đánh giá. Nếu class đã được phân giải, lỗi tiếp theo có thể nằm ở static member hoặc kiểu đối số.

## 11. Kiểm thử type reference

Kiểm thử nên xác nhận class được phân giải, static member trả đúng kết quả và context thực tế hỗ trợ type reference.

Ví dụ:

~~~java
@Test
void resolvesFullyQualifiedTypeReference() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 20)");

    assertEquals(20, expression.getValue(context, Integer.class));
}
~~~

Kiểm thử tên kiểu ngoài java.lang:

~~~java
@Test
void resolvesTypeFromFullyQualifiedPackageName() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY");

    assertEquals(
        java.time.DayOfWeek.MONDAY,
        expression.getValue(context, java.time.DayOfWeek.class)
    );
}
~~~

Nếu ứng dụng đăng ký import prefix, hãy kiểm thử cả tên ngắn và tên đầy đủ package. Nếu ứng dụng thay class loader hoặc dùng custom TypeLocator, test cần dùng đúng cấu hình đó.

Các trường hợp nên kiểm tra:

- Class trong java.lang.
- Class ngoài java.lang dùng tên đầy đủ package.
- Class dùng import prefix tùy chỉnh.
- Enum constant và static field.
- Static method có overload.
- Class không tồn tại hoặc không có trên classpath.
- Context không hỗ trợ type reference.
- TypeLocator bị giới hạn theo chính sách.
- Runtime class loader khác môi trường test.

## 12. Thực hành tốt

- Dùng cú pháp T(...) để tham chiếu class một cách tường minh.
- Dùng fully qualified name cho class ngoài java.lang khi cần biểu thức tự mô tả.
- Dùng tên đầy đủ package khi có khả năng trùng tên class.
- Chỉ đăng ký import prefix cần thiết trong StandardTypeLocator.
- Kiểm tra class loader nếu type resolution khác nhau giữa môi trường.
- Dùng static field và method cho các phép tính hoặc hằng số có ý nghĩa rõ.
- Kiểm thử overload và kiểu đối số của static method.
- Chọn StandardEvaluationContext khi biểu thức cần type reference.
- Không giả định SimpleEvaluationContext hỗ trợ T(...).
- Giới hạn TypeLocator và các quyền khác khi biểu thức đến từ nguồn bên ngoài.
- Không coi fully qualified name là biện pháp bảo mật.
- Chuyển logic phức tạp hoặc có tác dụng phụ sang method Java có kiểm soát.

## 13. Checklist review

Trước khi chấp nhận biểu thức có type reference, hãy kiểm tra:

- [ ] Cú pháp T(...) và tên class chính xác.
- [ ] Class có trên runtime classpath.
- [ ] Fully qualified name được dùng khi cần tránh nhập nhằng.
- [ ] Import prefix được đăng ký rõ ràng nếu dùng tên ngắn.
- [ ] TypeLocator dùng class loader phù hợp.
- [ ] Static field hoặc method thực sự tồn tại và có kiểu mong đợi.
- [ ] Overload được kiểm thử với kiểu đối số thực tế.
- [ ] EvaluationContext hỗ trợ type references.
- [ ] SimpleEvaluationContext không được giả định là hỗ trợ T(...).
- [ ] Nguồn biểu thức và phạm vi type resolution được kiểm soát.
- [ ] Có kiểm thử cho class hợp lệ, class thiếu và context bị giới hạn.

## Kết luận

Type reference **T(...)** cho phép SpEL phân giải một class Java để truy cập static field, static method, enum constant hoặc dùng trong phép kiểm tra kiểu. Với class ngoài java.lang, tên đầy đủ package giúp chỉ rõ class cần dùng mà không phụ thuộc import prefix. TypeLocator và class loader quyết định việc phân giải tên kiểu; StandardEvaluationContext hỗ trợ chức năng này, còn SimpleEvaluationContext không cung cấp type reference. Hãy cấu hình phạm vi type resolution có kiểm soát và kiểm thử biểu thức trong đúng context của ứng dụng.
