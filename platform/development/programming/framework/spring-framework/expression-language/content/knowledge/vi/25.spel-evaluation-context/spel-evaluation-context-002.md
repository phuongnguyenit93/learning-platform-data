# `SimpleEvaluationContext` và bề mặt đánh giá SpEL an toàn hơn

## Mục tiêu

`SimpleEvaluationContext` là một implementation của `EvaluationContext` dành cho các tình huống data binding và đánh giá biểu thức với một tập tính năng được giới hạn. Nó giúp ứng dụng chỉ mở những khả năng cần thiết cho rule hoặc biểu thức, thay vì mặc định cung cấp toàn bộ khả năng reflection như `StandardEvaluationContext`.

`SimpleEvaluationContext` phù hợp khi biểu thức cần đọc hoặc cập nhật property của một object, hoặc cần gọi một số instance method đã được cho phép. Nó loại trừ một số tính năng mạnh như type reference, constructor invocation và bean reference. Đây là một bề mặt đánh giá hẹp hơn, nhưng không phải sandbox hoàn chỉnh: getter hoặc method được cho phép vẫn có thể thực thi code, truy cập dữ liệu hoặc có tác dụng phụ.

## 1. Vì sao cần SimpleEvaluationContext?

`StandardEvaluationContext` cung cấp khả năng đánh giá SpEL đầy đủ hơn, bao gồm reflective property/method access, type references, constructor resolution, bean resolution khi được cấu hình và các cơ chế mở rộng khác. Sự linh hoạt này hữu ích cho biểu thức nội bộ do ứng dụng kiểm soát, nhưng có thể quá rộng khi đánh giá rule hoặc biểu thức đến từ cấu hình bên ngoài.

`SimpleEvaluationContext` được thiết kế cho các tình huống chỉ cần một phần cú pháp và quyền truy cập. Ứng dụng phải chọn rõ cách truy cập property và có muốn bật method invocation hay không.

| Tiêu chí | `SimpleEvaluationContext` | `StandardEvaluationContext` |
| --- | --- | --- |
| Mục tiêu | Data binding và biểu thức có tập quyền giới hạn. | Đánh giá SpEL với nhiều tính năng đầy đủ hơn. |
| Property access | Chọn data-binding accessors hoặc accessor tùy chỉnh. | Có reflective property access mặc định và có thể cấu hình thêm. |
| Ghi property | Có thể bật theo builder read-write và accessor hỗ trợ ghi. | Có thể ghi nếu accessor hỗ trợ. |
| Method invocation | Tắt mặc định; có thể bật instance methods rõ ràng. | Có reflective method resolution mặc định. |
| Type reference `T(...)` | Không hỗ trợ. | Hỗ trợ thông qua `TypeLocator`. |
| Constructor `new ...` | Không hỗ trợ. | Hỗ trợ thông qua `ConstructorResolver`. |
| Bean reference `@bean` | Không hỗ trợ. | Có thể hỗ trợ khi cấu hình `BeanResolver`. |

Chọn context theo đúng chức năng expression cần dùng. Nếu rule chỉ so sánh và đọc property, không cần bật method invocation hoặc chuyển sang context đầy đủ.

## 2. Tạo context chỉ đọc

Cách đơn giản nhất là dùng builder `forReadOnlyDataBinding()`. Context này cấu hình property access theo chế độ chỉ đọc và không bật method invocation:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

CustomerView customer = new CustomerView("Lan", true, 28);
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean eligible = expression.getValue(
        context, customer, Boolean.class);
```

Trong ví dụ này, SpEL đọc các property `active` và `age` từ root object `customer`, rồi tính kết quả Boolean. Expression không cần gọi method tùy ý, tạo object mới hoặc tham chiếu class.

Chế độ read-only có nghĩa là biểu thức không được dùng accessor data-binding này để ghi property. Nó không đảm bảo mọi getter đều thuần đọc: Java getter vẫn có thể chứa code, tải dữ liệu lazy hoặc truy cập tài nguyên. Vì vậy, hãy cung cấp các object view/DTO có getter đơn giản và tránh expose domain object có hành vi phức tạp.

## 3. Tạo context có thể ghi property

Nếu use case thực sự cần cập nhật property qua SpEL, dùng `forReadWriteDataBinding()`:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadWriteDataBinding()
        .build();

CustomerView customer = new CustomerView("Lan", true, 28);
Expression displayName = parser.parseExpression("displayName");
displayName.setValue(context, customer, "Linh");
```

Builder read-write cho phép data-binding property accessor thực hiện thao tác ghi trên những property có setter hoặc write path phù hợp. Property không hỗ trợ ghi vẫn không thể được cập nhật chỉ vì context ở chế độ read-write.

Chỉ bật read-write khi expression cần thay đổi object. Nếu rule chỉ kiểm tra điều kiện, dùng read-only giúp giảm khả năng một biểu thức vô tình sửa dữ liệu.

## 4. Bật instance method invocation khi thật sự cần

Method invocation bị tắt theo mặc định trong `SimpleEvaluationContext`. Nếu biểu thức cần gọi instance method, có thể bật rõ ràng bằng `withInstanceMethods()` trên builder:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
```

Ví dụ, khi cần gọi một method chuỗi:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("displayName.toUpperCase()");

String label = expression.getValue(context, customer, String.class);
```

Chỉ bật tính năng này nếu rule thực sự cần method invocation. Method được gọi trên object trong expression vẫn là Java code; một method có thể đọc database, thay đổi trạng thái hoặc thực hiện tác vụ tốn tài nguyên. Vì thế, chỉ expose object có method công khai phù hợp và có hợp đồng rõ ràng.

`withInstanceMethods()` không biến `SimpleEvaluationContext` thành `StandardEvaluationContext`: các tính năng bị loại trừ như type reference, constructor invocation và bean reference vẫn không được hỗ trợ.

## 5. Dùng property accessor tùy chỉnh

Ngoài hai chế độ data binding dựng sẵn, có thể tạo context từ một hoặc nhiều `PropertyAccessor` do ứng dụng chọn:

```java
EvaluationContext context = SimpleEvaluationContext
        .forPropertyAccessors(myReadOnlyAccessor)
        .build();
```

Đây là cách hữu ích khi expression chỉ nên nhìn thấy một tập property được allowlist hoặc khi dữ liệu có cấu trúc riêng không phù hợp với JavaBean data binding.

Accessor quyết định:

- Object và loại property nào có thể được truy cập.
- Property nào có thể đọc.
- Property nào có thể ghi, nếu accessor hỗ trợ ghi.
- Cách ánh xạ tên property trong expression sang dữ liệu thực tế.

Nếu dùng custom accessor, hãy giới hạn rõ loại target và tên property được expose. Không triển khai accessor kiểu “đọc mọi field hoặc gọi mọi getter” nếu mục tiêu là giới hạn bề mặt truy cập.

## 6. Root object, biến và đánh giá biểu thức

`SimpleEvaluationContext` vẫn là một `EvaluationContext`, nên có thể dùng root object và các biến phù hợp với API của context:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Expression expression = parser.parseExpression(
        "status == #expectedStatus and total <= #limit");

// Root object được truyền cho lần đánh giá.
// Biến expectedStatus và limit cần được cung cấp theo API context được dùng.
```

Trong ứng dụng, tạo context và đăng ký các giá trị đầu vào cần thiết trước khi đánh giá. Dùng tên biến có ý nghĩa và truyền dữ liệu dưới dạng object có kiểu rõ ràng. Tránh nối input vào source expression.

Ví dụ với root object:

```java
OrderView order = orderService.loadView(orderId);
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Boolean withinLimit = parser.parseExpression("total <= #limit")
        .getValue(context, order, Boolean.class);
```

Ở đây `total` được đọc từ root `order`, còn `#limit` là biến cần cung cấp trong context. Nếu ứng dụng cần biến, hãy dùng cơ chế variable registration được hỗ trợ bởi context phiên bản Spring đang dùng hoặc đưa giá trị đó vào một root view có kiểu rõ ràng.

## 7. Những tính năng SpEL không được hỗ trợ

`SimpleEvaluationContext` loại trừ các tính năng có thể mở rộng đáng kể quyền truy cập của biểu thức:

| Tính năng | Ví dụ với SpEL đầy đủ | Trong `SimpleEvaluationContext` |
| --- | --- | --- |
| Type reference | `T(java.lang.Math).max(1, 2)` | Không hỗ trợ. |
| Constructor invocation | `new java.math.BigDecimal('10.5')` | Không hỗ trợ. |
| Bean reference | `@pricingService.calculate(total)` | Không hỗ trợ. |
| Method invocation | `name.toUpperCase()` | Tắt mặc định; có thể opt-in instance methods. |
| Property access | `customer.name` | Phải chọn data-binding hoặc property accessor phù hợp. |

Điều này có nghĩa một expression cần `T(...)`, `new` hoặc `@bean` không thể chạy chỉ bằng cách bật thêm instance methods. Nếu use case thực sự cần các khả năng đó, hãy đánh giá lại thiết kế và dùng context phù hợp với một allowlist quyền truy cập chặt chẽ.

## 8. Read-only không đồng nghĩa với không có tác dụng phụ

Đây là giới hạn quan trọng khi chọn `SimpleEvaluationContext`.

Read-only chủ yếu kiểm soát khả năng ghi property qua accessor. Nó không thể bảo đảm getter hoặc method được gọi là thuần đọc. Ví dụ:

- Getter có thể khởi chạy lazy loading của ORM và phát sinh truy vấn database.
- Getter có thể đọc file cấu hình hoặc gọi một service khác.
- Instance method được bật có thể cập nhật counter, sửa cache hoặc gửi message.
- Một property accessor tùy chỉnh có thể thực hiện bất kỳ logic nào mà implementation cho phép.

Do đó, muốn expression có thể dự đoán được, hãy:

- Truyền DTO hoặc view object chứa dữ liệu đã chuẩn bị.
- Giữ getter đơn giản, không có side effect và không truy cập tài nguyên.
- Chỉ bật method invocation khi cần và giới hạn method có thể được gọi.
- Không expose repository, HTTP client, filesystem service hoặc object quản trị vào root/context.
- Thực hiện thao tác ghi hoặc truy cập hệ thống bên ngoài trong service layer, tại một bước được kiểm soát rõ ràng.

`SimpleEvaluationContext` giảm bề mặt tính năng có sẵn; độ an toàn thực tế vẫn phụ thuộc vào object, accessor, converter và method mà ứng dụng expose.

## 9. Chọn SimpleEvaluationContext hay StandardEvaluationContext

Có thể dùng các câu hỏi sau để chọn context:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chỉ đọc property để tính rule | `forReadOnlyDataBinding()` |
| Cập nhật property được phép qua data binding | `forReadWriteDataBinding()` |
| Chỉ expose một số property cụ thể | `forPropertyAccessors(...)` với accessor allowlist |
| Cần gọi instance method đã được cho phép | Builder của `SimpleEvaluationContext` kết hợp `withInstanceMethods()` |
| Cần `T(...)`, `new` hoặc `@bean` | `StandardEvaluationContext` với resolver/locator được giới hạn theo yêu cầu |
| Expression nội bộ cần đầy đủ tính năng SpEL | `StandardEvaluationContext` |

Đừng chuyển sang context đầy đủ chỉ để sửa một lỗi cú pháp nếu tính năng bị thiếu không thực sự cần thiết. Hãy xác định chính xác biểu thức cần quyền nào rồi expose quyền tối thiểu tương ứng.

## 10. Ví dụ cấu hình context theo từng mục đích

**Rule chỉ đọc:**

```java
EvaluationContext readOnly = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Boolean valid = parser.parseExpression(
        "active == true and balance >= 0")
        .getValue(readOnly, accountView, Boolean.class);
```

**Cập nhật property qua data binding:**

```java
EvaluationContext readWrite = SimpleEvaluationContext
        .forReadWriteDataBinding()
        .build();

parser.parseExpression("displayName")
        .setValue(readWrite, profileView, "Lan Nguyen");
```

**Cho phép instance method cần thiết:**

```java
EvaluationContext withMethods = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();

String normalized = parser.parseExpression("code.trim()")
        .getValue(withMethods, requestView, String.class);
```

Các ví dụ minh họa ba lựa chọn khác nhau. Trong ứng dụng thực tế, hãy tái sử dụng parser/expression phù hợp và tạo context với root object đúng cho mỗi lần đánh giá.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `T(...)` không hoạt động | `SimpleEvaluationContext` không hỗ trợ type references. | Dùng API Java để tính giá trị trước, hoặc chuyển sang context đầy đủ với type locator giới hạn nếu thật sự cần. |
| `new SomeType(...)` không hoạt động | Constructor invocation không thuộc tập tính năng của context này. | Tạo object trong Java rồi truyền vào root/variable phù hợp. |
| `@bean` không được phân giải | Bean references không được hỗ trợ. | Gọi service trong Java trước/sau khi đánh giá hoặc dùng context đầy đủ có BeanResolver được kiểm soát. |
| Gọi `name.toUpperCase()` thất bại | Method invocation đang tắt theo mặc định. | Chỉ khi cần, bật `withInstanceMethods()` và giới hạn object được expose. |
| `setValue` không ghi được property | Đang dùng read-only builder hoặc property không có write accessor/setter phù hợp. | Dùng read-write builder và kiểm tra property có thể ghi. |
| Không đọc được property | Property accessor hiện tại không hỗ trợ kiểu object/property đó. | Chọn data-binding builder phù hợp hoặc đăng ký accessor tùy chỉnh có allowlist. |
| Expression read-only vẫn phát sinh truy vấn | Getter hoặc accessor thực hiện lazy loading/truy cập tài nguyên. | Dùng DTO đã nạp dữ liệu và getter thuần đọc. |
| Expression gây hành động ngoài ý muốn | Instance method hoặc custom accessor có side effect. | Tắt method invocation nếu không cần; thu hẹp method/accessor và chuyển hành động sang service layer. |

## Ghi nhớ

- `SimpleEvaluationContext` cung cấp một tập tính năng SpEL giới hạn hơn cho data binding và rule evaluation.
- Dùng `forReadOnlyDataBinding()` khi chỉ cần đọc property.
- Dùng `forReadWriteDataBinding()` khi expression cần cập nhật property được phép.
- Method invocation tắt mặc định; `withInstanceMethods()` bật rõ ràng khi thật sự cần.
- `forPropertyAccessors(...)` cho phép ứng dụng kiểm soát property access bằng accessor đã chọn.
- Type reference `T(...)`, constructor `new` và bean reference `@bean` không được hỗ trợ.
- Read-only ngăn ghi qua accessor read-only nhưng không bảo đảm getter không có side effect.
- Không expose repository, HTTP client, filesystem service hoặc domain object có hành vi rộng cho expression bên ngoài.
- Dùng DTO/view object, getter đơn giản và allowlist property/method để giảm bề mặt truy cập.
- Chọn `StandardEvaluationContext` chỉ khi use case cần các tính năng đầy đủ hơn và ứng dụng có thể giới hạn quyền phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — DataBindingPropertyAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)