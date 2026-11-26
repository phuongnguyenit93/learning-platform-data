# Biểu thức đơn hoặc kết hợp literal, placeholder và SpEL

## 1. Mục tiêu và phạm vi

Trong chương **Biểu thức giá trị** của module **Spring Data Commons**, bài này tập trung vào cách đọc và viết một value expression: dùng một giá trị đơn hoặc kết hợp văn bản cố định, property placeholder và Spring Expression Language (SpEL).

Sau bài học, bạn cần làm được các việc sau:

- Nhận diện phần nào là văn bản nguyên dạng, phần nào lấy từ cấu hình, phần nào cần tính toán.
- Phân biệt biểu thức SpEL đơn với mẫu chuỗi chứa nhiều thành phần.
- Chọn đúng nguồn dữ liệu cho placeholder và SpEL.
- Dự đoán cả giá trị lẫn kiểu kết quả.
- Áp dụng biểu thức tại đúng điểm mở rộng mà module store hỗ trợ.

Spring Data Commons cung cấp abstraction dùng chung; repository và mapper của từng store quyết định nơi biểu thức được chấp nhận và context nào được cung cấp. Có hỗ trợ Value Expressions trong Commons không đồng nghĩa mọi annotation, mọi truy vấn hoặc mọi kho dữ liệu đều diễn giải cùng một chuỗi theo cùng cách.

## 2. Ba thành phần cơ bản

Giả sử ứng dụng có:

- Property cấu hình `app.stage=qa`.
- Biến SpEL `tenant` có giá trị `shop-a`.
- Biến SpEL `sequence` có giá trị số nguyên `42`.

Các ví dụ sau dùng đúng context giả định đó:

| Dạng | Ví dụ | Kết quả mong đợi |
| --- | --- | --- |
| Literal thuần | `orders` | Chuỗi `orders` |
| Placeholder đơn | `${app.stage}` | Chuỗi `qa` |
| SpEL đơn trả chuỗi | `#{#tenant}` | Chuỗi `shop-a` |
| SpEL đơn trả số | `#{#sequence + 1}` | Số nguyên `43` |
| Literal và placeholder | `orders-${app.stage}` | Chuỗi `orders-qa` |
| Literal và SpEL | `orders-#{#tenant}` | Chuỗi `orders-shop-a` |
| Literal, placeholder và SpEL | `orders-${app.stage}-#{#tenant}` | Chuỗi `orders-qa-shop-a` |

Dấu `${...}` biểu thị property placeholder. Dấu `#{...}` bao phần SpEL theo kiểu template. Phần văn bản nằm ngoài các khối đó là literal.

Tài liệu [Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html) xác định value expression có thể là một SpEL, một placeholder hoặc một biểu thức kết hợp các thành phần với literal.

Điểm quan trọng là nhận diện cú pháp trước khi suy luận kết quả. Chuỗi có vẻ giống phép tính chưa chắc đã được thực thi:

```text
1 + 2       -> literal "1 + 2"
#{1 + 2}    -> kết quả số 3
#{'1 + 2'}  -> kết quả chuỗi "1 + 2"
```

Ba đầu vào này có ý nghĩa khác nhau mặc dù đều chứa các ký tự `1 + 2`.

## 3. Biểu thức đơn

### 3.1. Literal: giữ nguyên nội dung

Literal không yêu cầu truy cập cấu hình hoặc thực hiện phép tính.

```text
orders
archive-v1
region=vn
```

Một literal thường phù hợp khi tên hoặc giá trị cố định là quyết định có chủ đích của ứng dụng. Không cần biến `orders` thành `#{'orders'}` chỉ để có hình thức giống một biểu thức.

Các dấu phân cách thông thường cũng được giữ lại. Ví dụ, `orders - qa` có khoảng trắng quanh dấu gạch ngang; không có quy tắc tự động biến nó thành `orders-qa`.

Literal ở ngoài SpEL không cần dấu nháy đơn. Nếu viết `'orders'` ở ngoài mọi khối, dấu nháy là một phần của văn bản đầu vào; nó không có vai trò giống dấu nháy của chuỗi trong SpEL.

### 3.2. Placeholder: lấy giá trị cấu hình

Placeholder hỏi `Environment` về một property:

```text
${app.stage}
${app.collection-prefix}
```

Nó không truy cập biến cục bộ do bạn đặt bằng `setVariable` trong SpEL. Ví dụ:

```text
${tenant}
```

biểu thị property có khóa `tenant`. Nó không có nghĩa là biến SpEL `#tenant`.

Có thể cung cấp giá trị mặc định:

```text
${app.stage:dev}
```

Trong ví dụ này:

- Có property `app.stage=qa`: kết quả là `qa`.
- Không có property `app.stage`: kết quả là `dev`.
- Có property nhưng giá trị là chuỗi rỗng: không nên coi dấu `:dev` là quy tắc thay thế mọi chuỗi rỗng.

Đây là fallback khi không phân giải được property theo quy tắc resolver, không phải bước kiểm tra tính hợp lệ của mọi cấu hình. Nếu `app.stage` bắt buộc nằm trong một tập giá trị, hãy xác thực cấu hình riêng.

Cú pháp placeholder và giá trị mặc định cũng được giải thích trong tài liệu [Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).

Với luồng `ValueExpressionParser` minh họa trong bài, placeholder được giải qua `Environment`. Không suy rộng mọi hành vi của cơ chế inject `@Value` sang API đánh giá trực tiếp, vì tầng tích hợp có thể thực hiện thêm bước xử lý hoặc chuyển kiểu.

### 3.3. SpEL: tính toán trên context

Một SpEL đơn có thể trả về nhiều kiểu giá trị:

```text
#{#tenant}           -> String khi tenant là chuỗi
#{#sequence + 1}     -> Integer khi sequence là Integer
#{#sequence > 10}    -> Boolean
#{'orders'}          -> String
```

Bên trong SpEL:

- `#tenant` truy cập biến có tên `tenant` trong evaluation context.
- `'orders'` là chuỗi literal của ngôn ngữ SpEL.
- `+` hoặc `>` là toán tử của SpEL, không còn là văn bản để giữ nguyên.

Một biểu thức SpEL đơn không bắt buộc trả về chuỗi. Điều này quan trọng khi nơi sử dụng mong đợi một số, một boolean hoặc một đối tượng cụ thể.

API `ValueExpression.evaluate(...)` trả về `Object` và có thể trả null. Kiểu kết quả phụ thuộc biểu thức và context; xem [ValueExpression API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpression.html).

Không dùng `String.valueOf(result)` quá sớm rồi xem đó là bằng chứng biểu thức đã trả về `String`. Phép chuyển đổi đó có thể che đi sự khác biệt giữa số `43` và chuỗi `"43"`.

## 4. Biểu thức kết hợp

### 4.1. Đọc theo từng đoạn

Xét mẫu:

```text
orders-${app.stage:dev}-#{#tenant}
```

Có thể phân tích theo cách sau:

| Đoạn | Loại | Nguồn giá trị | Kết quả trong ví dụ |
| --- | --- | --- | --- |
| `orders-` | Literal | Nội dung cố định | `orders-` |
| `${app.stage:dev}` | Placeholder | Environment | `qa` |
| `-` | Literal | Nội dung cố định | `-` |
| `#{#tenant}` | SpEL | EvaluationContext | `shop-a` |

Sau khi đánh giá các đoạn phù hợp, kết quả mong đợi là:

```text
orders-qa-shop-a
```

Dấu gạch ngang không được hệ thống tự thêm. Nó có mặt vì người viết đã đặt nó trong literal. Tương tự, dấu chấm, khoảng trắng và dấu gạch dưới trong mẫu vẫn có ý nghĩa riêng đối với kết quả cuối.

### 4.2. Chọn ranh giới biểu thức

Cùng tạo chuỗi nhưng có thể có hai cách viết:

```text
orders-#{#tenant}
#{'orders-' + #tenant}
```

Cách thứ nhất đặt phần cố định bên ngoài khối tính toán. Cách thứ hai là một khối SpEL duy nhất, trong đó phép cộng tạo chuỗi.

Khi chỉ ghép văn bản cố định với một giá trị, cách thứ nhất thường dễ đọc. Khi cần tính toán hoặc điều kiện gắn chặt với kết quả, một khối SpEL ngắn có thể diễn đạt rõ hơn.

Ví dụ chỉ dùng SpEL:

```text
#{'batch-' + (#sequence + 1)}
```

Kết quả mong đợi với `sequence=42` là chuỗi `batch-43`. Dấu ngoặc làm rõ rằng cần cộng số trước khi nối vào tiền tố.

Tài liệu [Expression Templating](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html) giải thích cách SpEL template kết hợp literal với các khối đánh giá. Khi thêm property placeholder vào cùng đầu vào, cần dùng cơ chế Value Expressions phù hợp thay vì chỉ giả định mọi SpEL parser đều tự đọc cấu hình.

### 4.3. Giữ các đoạn SpEL trả chuỗi khi trộn với placeholder

Với mẫu kết hợp placeholder và SpEL, nên chủ động làm rõ kiểu của từng đoạn:

```text
run-${app.stage}-#{#sequence.toString()}
```

Kết quả mong đợi là chuỗi `run-qa-42`.

Không dùng quy tắc “mọi đối tượng đều tự được nối thành chuỗi” cho tất cả implementation. Trong triển khai `CompositeValueExpression` của nhánh Spring Data Commons 3.5.x, kết quả từng thành phần được ép sang `String` khi ghép. Vì vậy, một đoạn SpEL trả `Integer` trực tiếp trong composite có thể gây lỗi ép kiểu; xem [mã nguồn CompositeValueExpression](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/java/org/springframework/data/expression/CompositeValueExpression.java).

So sánh:

```text
#{#sequence + 1}
    -> SpEL đơn, có thể giữ kết quả Integer

run-${app.stage}-#{(#sequence + 1).toString()}
    -> composite, chủ động tạo đoạn String "43"
```

Đây là hai mục đích khác nhau. Nếu cần một số để xử lý tiếp, giữ biểu thức số riêng. Nếu cần một tên hoặc nhãn dạng chuỗi, thể hiện việc tạo chuỗi ngay trong thiết kế biểu thức.

## 5. Ví dụ tự chứa với API Spring Data Commons

Ví dụ sau dựng context bằng Java, không cần repository hay kết nối database. Nó giúp quan sát cú pháp và kết quả trước khi tích hợp vào một store.

Các API `ValueExpressionParser` và `ValueEvaluationContext` có từ Spring Data Commons 3.3. Ví dụ sử dụng factory có tham số `create(SpelExpressionParser::new)`; đối chiếu [ValueExpressionParser API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpressionParser.html) khi áp dụng vào phiên bản của dự án.

```java
package com.example.expressions;

import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class ValueExpressionDemo {

    public static void main(String[] args) {
        StandardEnvironment environment = new StandardEnvironment();

        Map<String, Object> properties = Map.of(
                "app.stage", "qa",
                "app.prefix", "orders",
                "app.batch-size", "50");

        environment.getPropertySources().addFirst(
                new MapPropertySource("lesson-properties", properties));

        StandardEvaluationContext spelContext =
                new StandardEvaluationContext();

        spelContext.setVariable("tenant", "shop-a");
        spelContext.setVariable("sequence", 42);

        ValueEvaluationContext context =
                ValueEvaluationContext.of(environment, spelContext);

        ValueExpressionParser parser =
                ValueExpressionParser.create(SpelExpressionParser::new);

        String[] samples = {
                "orders",
                "${app.stage}",
                "${app.unknown:dev}",
                "#{#tenant}",
                "#{#sequence + 1}",
                "orders-${app.stage}",
                "orders-#{#tenant}",
                "${app.prefix}-${app.stage}-#{#tenant}",
                "run-${app.stage}-#{#sequence.toString()}"
        };

        for (String sample : samples) {
            ValueExpression expression = parser.parse(sample);
            Object result = expression.evaluate(context);

            String resultType = result == null
                    ? "null"
                    : result.getClass().getSimpleName();

            System.out.println(
                    sample + " -> " + result + " [" + resultType + "]");
        }
    }
}
```

Kết quả dự kiến của các mẫu đã khai báo:

```text
orders -> orders [String]
${app.stage} -> qa [String]
${app.unknown:dev} -> dev [String]
#{#tenant} -> shop-a [String]
#{#sequence + 1} -> 43 [Integer]
orders-${app.stage} -> orders-qa [String]
orders-#{#tenant} -> orders-shop-a [String]
${app.prefix}-${app.stage}-#{#tenant} -> orders-qa-shop-a [String]
run-${app.stage}-#{#sequence.toString()} -> run-qa-42 [String]
```

Có hai nguồn dữ liệu độc lập:

1. `MapPropertySource` đưa property vào `Environment`.
2. `setVariable` đưa biến vào `StandardEvaluationContext`.

`ValueEvaluationContext.of(environment, spelContext)` kết hợp hai nguồn đó để đánh giá value expression. Xem [ValueEvaluationContext API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueEvaluationContext.html).

Ví dụ dùng property source được thêm vào đầu danh sách để các khóa minh họa có độ ưu tiên rõ ràng. Đây là cách dựng dữ liệu cho bài học, không có nghĩa API Commons tự động tải `application.yml` vào một `StandardEnvironment` do bạn tự tạo.

## 6. Context quyết định ý nghĩa tên tham chiếu

### 6.1. Property và biến không phải cùng một không gian tên

Dù đều mang tên `tenant`, hai biểu thức sau có thể trả hai giá trị khác nhau:

```text
${tenant}
#{#tenant}
```

Nếu property `tenant=platform` và biến SpEL `tenant=shop-a` thì:

| Biểu thức | Nguồn đọc | Kết quả |
| --- | --- | --- |
| `${tenant}` | Environment | `platform` |
| `#{#tenant}` | Biến SpEL | `shop-a` |

Không có quy tắc tự đồng bộ hai giá trị này. Khi cấu hình ứng dụng và dữ liệu của một lần gọi cần có vai trò khác nhau, dùng tên rõ nghĩa giúp tránh hiểu nhầm.

### 6.2. Tên không có dấu # cũng không tự trở thành property cấu hình

Biểu thức:

```text
#{tenant}
```

được SpEL diễn giải trong ngữ cảnh thuộc tính hoặc đối tượng gốc của nó. Nó không đồng nghĩa `#{#tenant}`, và cũng không phải cách viết khác của `${tenant}`.

Tương tự:

```text
#{app.stage}
```

không có nghĩa “đọc property Environment tên app.stage”. Dấu chấm thuộc cú pháp truy cập trong SpEL.

Trong ví dụ Java, biến đã được khai báo bằng `setVariable("tenant", ...)`, nên cách tham chiếu tương ứng là `#tenant`.

### 6.3. Bean, tham số phương thức và biến do store cung cấp

SpEL có các cơ chế tham chiếu khác như truy cập bean thông qua bean resolver hoặc truy cập đối tượng gốc. Chúng chỉ hoạt động khi evaluation context có hạ tầng tương ứng.

Một `StandardEvaluationContext` bạn tự tạo không tự biết mọi bean Spring. Tương tự, biến đặt trong chương trình demo không tự xuất hiện trong context của repository hoặc annotation mapping.

Khi chuyển biểu thức từ ví dụ Java vào ứng dụng, cần trả lời:

- Nơi sử dụng lấy `Environment` từ đâu?
- Ai tạo evaluation context?
- Biến hoặc thuộc tính cần đọc đã được cung cấp chưa?
- Điểm mở rộng đó mong đợi kết quả kiểu gì?

Bài này tập trung vào cấu trúc biểu thức; việc mở rộng context cần dựa vào cơ chế của nơi tích hợp cụ thể.

## 7. Những quy tắc giúp tránh biểu thức sai nghĩa

### 7.1. Placeholder không phải phép tính SpEL

```text
${1 + 2}
```

yêu cầu phân giải một property có tên tương ứng. Nó không thực hiện phép cộng.

Dùng:

```text
#{1 + 2}
```

nếu mục tiêu là tính số.

Tương tự, nếu property `app.batch-size` chứa chuỗi `50`, việc phân giải `${app.batch-size}` chưa có nghĩa là bạn đang có một đối tượng `Integer` để cộng số.

Nếu muốn dùng property đó cho tính toán trong ví dụ Java, có thể đọc kiểu rõ ràng rồi cung cấp biến:

```java
Integer batchSize = environment.getRequiredProperty(
        "app.batch-size", Integer.class);

spelContext.setVariable("batchSize", batchSize);

Object nextSize = parser.parse("#{#batchSize + 10}")
        .evaluate(ValueEvaluationContext.of(environment, spelContext));

// Với app.batch-size=50, nextSize là Integer có giá trị 60.
```

Đoạn này tiếp nối các biến Java trong chương trình minh họa. Bước đọc property có kiểu được thực hiện tường minh trước khi đánh giá SpEL.

### 7.2. Không suy luận một thứ tự thay thế toàn cục

Một cách suy luận dễ gây lỗi là:

```text
Bước 1: thay tất cả ${...} trong mọi vị trí.
Bước 2: diễn giải toàn bộ chuỗi còn lại như SpEL.
```

Không dùng mô hình này như hợp đồng chung cho mọi value expression. Parser có thể phân loại và xử lý các đoạn theo cơ chế riêng; còn tầng tích hợp `@Value` hoặc một module store có thể có pipeline bổ sung.

Để kết hợp dễ hiểu, ưu tiên các đoạn độc lập:

```text
orders-${app.stage:dev}-#{#tenant}
```

Nếu cần tính toán trên một property, đọc property có kiểu và cung cấp nó vào context như ví dụ `batchSize`. Cách này làm rõ dữ liệu được lấy từ đâu và khi nào được chuyển kiểu.

Cũng không mặc định rằng một chuỗi do placeholder trả về sẽ được parse tiếp thành mã SpEL. Giá trị cấu hình và cú pháp biểu thức cần được phân biệt rõ.

### 7.3. Phân biệt fallback của placeholder và SpEL

```text
${app.stage:dev}
#{#tenant ?: 'public'}
```

Hai fallback xử lý hai nguồn dữ liệu khác nhau:

- `:dev` thuộc cú pháp placeholder, dùng khi property không được phân giải theo quy tắc tương ứng.
- `?: 'public'` là toán tử Elvis của SpEL, áp dụng cho kết quả biểu thức trước nó, bao gồm xử lý null hoặc chuỗi rỗng theo quy tắc SpEL.

Một chuỗi toàn khoảng trắng không tự trở thành cấu hình hợp lệ chỉ nhờ có fallback. Nếu cần chuẩn hóa hoặc xác thực, hãy thể hiện quy tắc đó ở nơi phù hợp.

### 7.4. Khoảng trắng và dấu nháy có thể thay đổi kết quả

```text
orders-#{#tenant}
orders - #{#tenant}
```

Hai mẫu tạo chuỗi khác nhau vì literal chứa khoảng trắng khác nhau.

Với chuỗi trong Java:

```java
String expression = "orders-${app.stage}-#{#tenant}";
```

dấu nháy kép là ký hiệu khai báo chuỗi của Java. Nó không phải ký tự thuộc value expression.

Bên trong SpEL:

```text
#{'orders-' + #tenant}
```

dấu nháy đơn xác định một chuỗi của ngôn ngữ SpEL.

Trước khi xử lý một biểu thức dài, hãy phân biệt ba lớp: cú pháp chuỗi của ngôn ngữ chứa nó, cú pháp Value Expressions và cú pháp bên trong SpEL.

## 8. Áp dụng vào Spring Data đúng phạm vi

### 8.1. Mapping metadata

Một số module Spring Data có mapping model riêng cho phép biểu thức trong những annotation được hỗ trợ. Với một giá trị tên dạng:

```text
orders-${app.stage:dev}-#{#tenant}
```

bạn phải xác minh annotation đó có hỗ trợ value expression và context thực tế có biến `tenant` hay không. Kết quả đánh giá được trong chương trình demo chưa chứng minh rằng nó dùng được nguyên trạng trong annotation.

Tài liệu Commons phân biệt các module có mapping model riêng với các module dựa trên mapping model của thư viện khác, chẳng hạn JPA và LDAP. Không chuyển giả định từ annotation mapping của MongoDB sang `@Table` hoặc `@Column` của Jakarta Persistence. Tham khảo phần Scope trong [Value Expressions Fundamentals của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/value-expressions.html).

Nếu tên collection, index hoặc đích ánh xạ có thể thay đổi theo context, cần kiểm tra cả thời điểm module đánh giá và cách module sử dụng metadata đó.

### 8.2. Repository query

Trong các module có hỗ trợ biểu thức tại query method, cú pháp bao quanh biểu thức còn liên quan đến cách bind tham số.

Các dạng như:

```text
:#{...}
?#{...}
:${...}
?${...}
```

là ví dụ về ký hiệu tích hợp được tài liệu Commons nhắc đến; không phải mọi store đều chấp nhận cả bốn dạng. Dấu `:` hoặc `?` không thuộc cú pháp nền của `ValueExpressionParser` khi bạn chỉ đánh giá một giá trị trong Java.

Không biến chuỗi query thành một mẫu nối văn bản tùy ý rồi giả định rằng đó là parameter binding. Giá trị dữ liệu, tên trường và cấu trúc truy vấn có vai trò khác nhau; cần theo đúng hợp đồng của module query đang dùng.

### 8.3. Các abstraction khác

Derived query phân tích tên phương thức repository theo quy tắc của module. Viết tên phương thức hoặc tên thuộc tính dưới dạng có `#{...}` không tự tạo ra derived query động.

Tương tự, `Pageable`, `Sort` và projection có hợp đồng riêng. Chỉ đưa value expression vào những điểm mở rộng đã được tài liệu xác định là hỗ trợ. Đây là cách dùng abstraction chung mà vẫn tôn trọng khả năng của từng store.

## 9. Parse, evaluate và kiểm tra kiểu

Hai thao tác cần được tách về mặt tư duy:

```text
Chuỗi khai báo
    -> parse
    -> ValueExpression đã phân tích
    -> evaluate với context
    -> giá trị kết quả
```

### 9.1. Lỗi khi parse

Ví dụ một SpEL thiếu toán hạng:

```text
#{1 + }
```

có thể bị từ chối khi parser phân tích cú pháp.

Việc parse thành công chỉ chứng minh đầu vào đã được parser chấp nhận. Nó chưa chứng minh mọi tham chiếu có thể phân giải hoặc kết quả có đúng kiểu nơi sử dụng mong đợi.

### 9.2. Lỗi hoặc giá trị bất ngờ khi evaluate

Một số trường hợp cần kiểm tra lúc đánh giá:

| Hiện tượng | Nguyên nhân cần xem xét |
| --- | --- |
| Placeholder bắt buộc không tồn tại | Environment thiếu property hoặc chọn sai tên khóa |
| SpEL không tìm thấy thuộc tính | Context không có đối tượng gốc hoặc thuộc tính tương ứng |
| Biến SpEL cho null | Biến chưa được cung cấp hoặc giá trị vốn là null |
| Composite gặp lỗi ép kiểu | Một đoạn không trả kiểu chuỗi như cơ chế ghép yêu cầu |
| Kết quả đúng nội dung nhưng sai kiểu | Đã chuyển một giá trị số thành nhãn chuỗi |
| Tên đích có dấu cách ngoài ý muốn | Literal chứa khoảng trắng hoặc cấu hình không được chuẩn hóa |

Với đường đánh giá placeholder của Commons được minh họa, implementation sử dụng `resolveRequiredPlaceholders` và chuyển lỗi phân giải thành lỗi đánh giá; xem [PlaceholderExpression](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/expression/PlaceholderExpression.java).

Không gộp mọi trường hợp thành “lỗi cú pháp”. Một biểu thức đúng cú pháp vẫn có thể thiếu dữ liệu hoặc vi phạm hợp đồng kiểu.

### 9.3. Tái sử dụng biểu thức đã parse

Có thể parse một lần rồi đánh giá lại với context phù hợp. Điều này giúp tránh lặp lại chi phí phân tích.

Tuy nhiên, cache đối tượng biểu thức và cache kết quả là hai quyết định khác nhau. Biểu thức:

```text
orders-${app.stage}-#{#tenant}
```

có thể cho kết quả khác nhau khi context thay đổi. Không lưu kết quả đầu tiên vào một biến toàn cục rồi dùng chung cho mọi lần đánh giá có tenant khác nhau.

Việc chia sẻ đối tượng biểu thức cũng không có nghĩa một evaluation context có trạng thái thay đổi nên được sửa đồng thời giữa nhiều request. Hãy quản lý dữ liệu theo vòng đời sử dụng thực tế.

Biểu thức nên đến từ nguồn khai báo tin cậy do ứng dụng kiểm soát. Dữ liệu người dùng nên được cung cấp dưới dạng giá trị hoặc tham số, thay vì được ghép thành mã SpEL để parse và thực thi.

## 10. Bài thực hành và tiêu chí hoàn thành

Dùng chương trình ở mục 5, sau đó thực hiện:

1. Đổi `app.stage` từ `qa` sang `prod` và dự đoán các mẫu nào thay đổi.
2. Giữ nguyên property nhưng đổi biến `tenant` từ `shop-a` sang `shop-b`.
3. So sánh `#{#sequence + 1}` với `#{'seq-' + (#sequence + 1)}` về cả giá trị và kiểu.
4. Bỏ property `app.stage`; so sánh placeholder có fallback với placeholder bắt buộc.
5. Cung cấp property `tenant=platform` đồng thời giữ biến SpEL `tenant=shop-b`; so sánh hai cách tham chiếu.
6. Đặt một property thành chuỗi rỗng và quan sát sự khác biệt giữa fallback, chuẩn hóa và xác thực.
7. Viết một mẫu gồm literal, hai placeholder và một đoạn SpEL trả chuỗi.

Mẫu dữ liệu để ghi kết quả quan sát:

| Biểu thức | Property liên quan | Biến/context liên quan | Giá trị mong đợi | Kiểu mong đợi |
| --- | --- | --- | --- | --- |
| `${app.stage:dev}` | `app.stage` | Không dùng biến SpEL | Theo cấu hình hoặc `dev` | String |
| `#{#sequence + 1}` | Không dùng placeholder | `sequence` | Tổng số học | Integer trong ví dụ |
| `orders-${app.stage:dev}-#{#tenant}` | `app.stage` | `tenant` dạng String | Tên ghép theo context | String |

Bài thực hành đạt yêu cầu khi bạn giải thích được từng đoạn của biểu thức, chỉ ra nguồn dữ liệu tương ứng và dự đoán được kiểu kết quả trước khi tích hợp vào repository hoặc mapping metadata.
