# Static import và tên ngắn

## 1. Vai trò trong DSL nội bộ

DSL nội bộ (internal hoặc embedded Domain-Specific Language) được xây dựng bằng cú pháp của một ngôn ngữ lập trình chủ. Trong Java, nhóm phát triển có thể tạo các lớp, phương thức, đối tượng và biểu thức fluent để người dùng mô tả một quy tắc hoặc quy trình theo thuật ngữ của miền.

Một vấn đề thường gặp là tên lớp và tên phương thức làm biểu thức dài hơn ý định cần diễn đạt. Ví dụ, một lời gọi có thể phải viết đầy đủ tên lớp:

```java
Rule rule = RuleDsl.rule("paid-order")
    .when(Conditions.all(
        Conditions.equalTo("status", "PAID"),
        Conditions.greaterThan("amount", 0)
    ))
    .then(Actions.markEligible());
```

Java cung cấp `static import` để cho phép tham chiếu trực tiếp đến thành viên `static` mà không phải ghi tên lớp chứa thành viên đó. Kết hợp với cách đặt tên ngắn, rõ nghĩa và API fluent, kỹ thuật này có thể làm DSL nội bộ gọn hơn:

```java
import static example.rules.RuleDsl.rule;
import static example.rules.Conditions.all;
import static example.rules.Conditions.equalTo;
import static example.rules.Conditions.greaterThan;
import static example.rules.Actions.markEligible;

Rule rule = rule("paid-order")
    .when(all(
        equalTo("status", "PAID"),
        greaterThan("amount", 0)
    ))
    .then(markEligible());
```

Hai đoạn mã có thể tạo cùng một cấu trúc quy tắc nếu các API tương ứng được định nghĩa như nhau. Đoạn thứ hai ít lặp tên lớp hơn, nhờ đó người đọc tập trung vào các khái niệm `rule`, `when`, `all`, `equalTo` và `markEligible`.

Static import và tên ngắn là kỹ thuật trình bày API. Chúng không tự tạo ra cú pháp mới trong Java, không thay đổi ngữ nghĩa của phương thức và không biến Java thành một ngôn ngữ có parser riêng. DSL vẫn chịu các quy tắc cú pháp, kiểu dữ liệu và biên dịch của Java.

## 2. Static import trong Java là gì?

`import static` là khai báo cho phép sử dụng thành viên `static` của một kiểu bằng tên đơn giản trong tệp nguồn. Tính năng này có từ Java 5.

Không dùng static import:

```java
double larger = Math.max(12.5, 18.0);
double circleArea = Math.PI * radius * radius;
```

Dùng static import:

```java
import static java.lang.Math.PI;
import static java.lang.Math.max;

double larger = max(12.5, 18.0);
double circleArea = PI * radius * radius;
```

Các thành viên vẫn thuộc về `java.lang.Math`; static import chỉ cho phép dùng tên `max` và `PI` trực tiếp trong phạm vi tệp nguồn có khai báo import.

### 2.1. Import một thành viên cụ thể

Cú pháp:

```java
import static ten_goi.TenKieu.tenThanhVien;
```

Ví dụ:

```java
import static java.lang.Math.sqrt;
import static java.lang.Math.PI;

double diagonal = sqrt(3 * 3 + 4 * 4);
double circumference = 2 * PI * radius;
```

Import từng thành viên làm rõ tên nào được đưa vào phạm vi sử dụng và giảm nguy cơ xung đột tên. Đây thường là lựa chọn phù hợp khi chỉ cần một vài hàm hoặc hằng số.

### 2.2. Static import on demand

Cú pháp:

```java
import static ten_goi.TenKieu.*;
```

Ví dụ:

```java
import static java.lang.Math.*;

double result = max(10, min(20, 15));
double circumference = 2 * PI * radius;
```

Dấu `*` cho phép tham chiếu các thành viên `static` có thể truy cập của kiểu được chỉ định. Nó không import các thành viên instance, không import các kiểu thuộc những package khác và không tự động đưa mọi thành viên của các kiểu liên quan vào phạm vi.

Static import on demand ngắn trong phần khai báo, nhưng có thể làm người đọc khó biết một tên hàm đến từ lớp nào. Với DSL có nhiều hàm tên chung như `all`, `any`, `equalTo`, `value` hoặc `of`, import cụ thể thường giúp mã dễ truy vết hơn.

### 2.3. Thành viên nào có thể được static import?

Có thể static import các thành viên `static` được phép truy cập, chẳng hạn:

- Phương thức `static`.
- Trường `static`, gồm cả hằng số `public static final`.
- Hằng số enum, vì mỗi hằng số enum là một trường `static` của kiểu enum.
- Kiểu thành viên `static` (static member type).

Không thể static import phương thức instance hoặc trường instance. Ví dụ, `String.length()` là phương thức instance, vì vậy không thể viết `import static java.lang.String.length;` để gọi `length()` độc lập.

Static import vẫn tuân theo quy tắc truy cập của Java. Một thành viên `private` hoặc thành viên không thể truy cập từ vị trí khai báo import không trở nên khả dụng chỉ vì dùng `import static`.

### 2.4. Static import không tạo bí danh

Java không cho phép đặt alias cho thành viên trong câu lệnh static import. Ví dụ sau không phải cú pháp Java hợp lệ:

```java
// Không hợp lệ trong Java:
import static java.lang.Math.max as larger;
```

Nếu cần tên khác, có thể tạo một phương thức wrapper có tên phù hợp trong lớp DSL:

```java
public final class NumberDsl {
    private NumberDsl() {}

    public static int larger(int left, int right) {
        return Math.max(left, right);
    }
}
```

Sau đó:

```java
import static example.dsl.NumberDsl.larger;

int result = larger(12, 20);
```

Wrapper nên được tạo khi tên mới có ý nghĩa miền rõ ràng hoặc che giấu được một chi tiết kỹ thuật hữu ích. Không nên tạo hàng loạt wrapper chỉ để thay đổi vài ký tự.

## 3. Tạo tên ngắn cho DSL nội bộ

Static import chỉ bỏ phần định danh kiểu khỏi lời gọi. Độ dễ đọc của DSL vẫn phụ thuộc chủ yếu vào tên phương thức, tham số, kiểu trả về và cách kết hợp biểu thức.

### 3.1. Ưu tiên từ vựng của miền

Tên nên mô tả điều người dùng muốn làm trong miền. Ví dụ:

| Tên kỹ thuật hoặc quá chung | Tên gắn với miền rõ hơn |
|---|---|
| `executeOperation()` | `approveOrder()` |
| `setFlag(true)` | `markEligible()` |
| `checkValue()` | `isPaid()` |
| `processData()` | `groupOrdersByCustomer()` |
| `createObject()` | `rule("paid-order")` |

Tên miền giúp người đọc hiểu ý định mà không cần lần theo cách triển khai. Tuy nhiên, tên cần chính xác. Không nên gọi một thao tác là `validate` nếu nó thực tế chỉ kiểm tra một điều kiện nhỏ hoặc có tác dụng phụ khác.

### 3.2. Ngắn nhưng vẫn có nghĩa

Tên ngắn hữu ích khi nó là từ vựng quen thuộc, có nghĩa rõ và được dùng nhất quán. Những tên như `all`, `any`, `not`, `eq`, `gt`, `source` hoặc `where` có thể phù hợp trong một miền có quy ước rõ ràng.

Ngược lại, tên viết tắt khó hiểu như `proc`, `cfg`, `val`, `op1` hoặc một ký tự đơn có thể làm biểu thức ngắn hơn nhưng tăng chi phí đọc và bảo trì. Nếu tên không thể hiểu khi đứng trong ngữ cảnh lời gọi, nên dùng tên dài hơn.

Một nguyên tắc thực tế là dùng tên ngắn cho khái niệm cơ bản, phổ biến và có ngữ nghĩa ổn định; dùng tên đầy đủ cho thao tác ít gặp, dễ nhầm hoặc có tác động quan trọng.

### 3.3. Dùng cùng một phong cách đặt tên

Các hàm cùng vai trò nên tuân theo một quy ước. Ví dụ, nếu nhóm dùng động từ cho hành động, hãy giữ nhất quán giữa `filter`, `groupBy`, `sortBy` và `aggregate`. Nếu nhóm dùng tên mô tả điều kiện dạng `isPaid`, `hasAddress`, `isOverdue`, hãy tránh trộn lẫn tùy tiện với những tên không cùng cấu trúc.

Với Java, tên phương thức và biến thường dùng `lowerCamelCase`; tên kiểu dùng `UpperCamelCase`; hằng số thường dùng `UPPER_SNAKE_CASE`. DSL nội bộ vẫn nên tôn trọng quy ước Java trừ khi có lý do rõ ràng để chọn cách khác.

## 4. Xây dựng lớp DSL với các phương thức static

Một cách triển khai phổ biến là gom các hàm tạo biểu thức hoặc đối tượng miền vào một lớp tiện ích có constructor private. Các hàm này thường là factory method.

Ví dụ minh họa:

```java
package example.rules;

public final class Conditions {
    private Conditions() {
    }

    public static Condition equalTo(String field, Object value) {
        return new ComparisonCondition(field, Operator.EQUALS, value);
    }

    public static Condition greaterThan(String field, Number value) {
        return new ComparisonCondition(field, Operator.GREATER_THAN, value);
    }

    public static Condition all(Condition... conditions) {
        return new AllCondition(conditions);
    }
}
```

Các kiểu `Condition`, `ComparisonCondition`, `Operator` và `AllCondition` là các kiểu miền giả định. Phần cài đặt thật phụ thuộc mô hình của DSL.

Khi import các hàm:

```java
import static example.rules.Conditions.all;
import static example.rules.Conditions.equalTo;
import static example.rules.Conditions.greaterThan;

Condition condition = all(
    equalTo("status", "PAID"),
    greaterThan("amount", 0)
);
```

Đoạn mã thể hiện cấu trúc điều kiện gần với cách người dùng diễn đạt: tất cả các điều kiện con phải đúng. `all` trả về một đối tượng biểu diễn điều kiện tổng hợp, thay vì tự thực hiện việc lọc dữ liệu ngay lúc tạo biểu thức.

### 4.1. Tách nhóm hàm theo trách nhiệm

Không nên dồn mọi phương thức static của DSL vào một lớp lớn. Có thể chia theo nhóm khái niệm:

| Lớp | Trách nhiệm | Một số phương thức |
|---|---|---|
| `RuleDsl` | Tạo và khai báo quy tắc | `rule`, `when`, `then` |
| `Conditions` | Tạo biểu thức điều kiện | `all`, `any`, `not`, `equalTo`, `greaterThan` |
| `Actions` | Tạo hành động | `markEligible`, `reject`, `notify` |
| `Fields` | Tham chiếu trường miền | `field`, `attribute` |
| `Values` | Tạo hoặc chuẩn hóa giá trị miền | `value`, `literal` |

Các tên trong bảng chỉ là ví dụ. Ranh giới lớp nên dựa vào mô hình miền và trách nhiệm thực tế. Một nhóm hàm quá nhỏ có thể làm import rườm rà; một lớp quá rộng lại khiến tên thành viên dễ xung đột và khó tìm.

### 4.2. Ví dụ DSL nội bộ hoàn chỉnh ở mức biểu đạt

Giả sử thư viện cung cấp các factory method và đối tượng fluent, người dùng có thể viết:

```java
import static example.rules.RuleDsl.rule;
import static example.rules.Conditions.all;
import static example.rules.Conditions.equalTo;
import static example.rules.Conditions.greaterThan;
import static example.rules.Actions.markEligible;

Rule paidOrder = rule("paid-order")
    .when(all(
        equalTo("status", "PAID"),
        greaterThan("amount", 0)
    ))
    .then(markEligible());
```

Đoạn mã cho thấy sự phối hợp giữa hai kỹ thuật:

- Static import làm các factory method có thể được gọi trực tiếp bằng tên đơn giản.
- Fluent API cho phép gọi tiếp các phương thức instance như `.when(...)` và `.then(...)` trên đối tượng được trả về.

Hai kỹ thuật có vai trò khác nhau. Static import rút gọn tên lớp ở lời gọi static; fluent API tổ chức chuỗi thao tác trên một đối tượng. Chúng có thể kết hợp để tạo cách viết DSL tự nhiên hơn.

## 5. Phân biệt static import và lời gọi fluent

Hai hình thức thường xuất hiện cạnh nhau trong DSL nội bộ, nhưng cơ chế Java khác nhau.

| Đặc điểm | Static import | Fluent API |
|---|---|---|
| Mục đích | Cho phép dùng tên thành viên static không kèm tên kiểu | Nối nhiều thao tác qua giá trị trả về của đối tượng |
| Cơ chế | Quy tắc import và phân giải tên của Java | Lời gọi phương thức instance hoặc builder |
| Ví dụ | `all(a, b)` | `rule("x").when(condition).then(action)` |
| Thành phần cần có | Thành viên static truy cập được | Đối tượng có các phương thức phù hợp |
| Có thể dùng riêng? | Có | Có |

Ví dụ kết hợp:

```java
import static example.rules.Conditions.equalTo;

Rule rule = RuleDsl.rule("paid-order")
    .when(equalTo("status", "PAID"))
    .then(Actions.markEligible());
```

Ở đây `equalTo` được gọi qua static import, còn `when` và `then` là lời gọi instance trên đối tượng `RuleBuilder` (giả định kiểu trả về của `RuleDsl.rule`).

## 6. Static import trong API của DSL: những lựa chọn quan trọng

### 6.1. Import tường minh hay import wildcard?

Hai cách viết:

```java
import static example.rules.Conditions.equalTo;
import static example.rules.Conditions.greaterThan;
import static example.rules.Conditions.all;
```

và:

```java
import static example.rules.Conditions.*;
```

Import tường minh có các lợi ích:

- Người đọc biết các hàm ngắn đến từ đâu.
- IDE và code review dễ nhận ra thành viên đang được dùng.
- Giảm nguy cơ thêm một import mới làm tên gọi trở nên khó phân giải.
- Dễ kiểm soát bề mặt API mà tệp đang sử dụng.

Wildcard có thể tiện khi một lớp DSL cung cấp một nhóm hàm nhỏ, ổn định và thường được dùng cùng nhau. Tuy nhiên, khi lớp phát triển hoặc nhiều lớp cùng có tên phương thức phổ biến, wildcard có thể làm tăng xung đột và giảm khả năng truy vết.

Với mã nguồn thư viện hoặc mã cần bảo trì lâu dài, nên ưu tiên import tường minh cho các nhóm hàm quan trọng. Nếu dự án chọn wildcard, cần có quy ước thống nhất và giữ số nhóm static import ở mức dễ hiểu.

### 6.2. Chọn một lớp facade hay nhiều lớp DSL?

Một lớp facade duy nhất có thể tạo trải nghiệm đơn giản:

```java
import static example.dsl.Dsl.*;
```

Ưu điểm là ít khai báo import. Hạn chế là lớp `Dsl` có thể trở thành nơi chứa quá nhiều hàm, tên chung dễ xung đột và trách nhiệm khó phân chia.

Nhiều lớp theo miền có thể làm import dài hơn:

```java
import static example.dsl.Rules.rule;
import static example.dsl.Conditions.all;
import static example.dsl.Actions.notifyOwner;
```

Đổi lại, nguồn gốc và trách nhiệm của từng hàm rõ ràng hơn. Một giải pháp trung gian là cung cấp facade cho các trường hợp thông dụng, đồng thời giữ các lớp chuyên biệt để người dùng có thể import chọn lọc.

### 6.3. Tên phương thức trùng nhau

Nhiều DSL có các tên rất phổ biến như `of`, `value`, `all`, `any`, `not`, `get` hoặc `create`. Nếu import nhiều thành viên trùng tên từ các kiểu khác nhau, lời gọi có thể trở nên khó hiểu hoặc không phân giải được.

Ví dụ minh họa tình huống xung đột:

```java
import static example.rules.Conditions.value;
import static example.config.ConfigValues.value;

// Lời gọi value(...) có thể mơ hồ nếu cả hai phương thức phù hợp.
```

Khi có xung đột, có thể gọi đầy đủ tên kiểu tại vị trí cần thiết:

```java
Condition condition = Conditions.value("status");
ConfigValue config = ConfigValues.value("region");
```

Hoặc đổi thiết kế API để tên phản ánh rõ miền, chẳng hạn `fieldValue(...)` và `configValue(...)`. Không nên cố làm mọi tên ngắn giống nhau nếu chúng đại diện cho khái niệm khác nhau.

### 6.4. Overload cần có chủ đích

Java cho phép overload phương thức, do đó DSL có thể có các dạng:

```java
equalTo("status", "PAID");
equalTo("retryCount", 3);
equalTo("enabled", true);
```

Overload thuận tiện khi các lời gọi có cùng ý nghĩa và khác kiểu đầu vào. Nhưng overload quá nhiều, đặc biệt với `null`, kiểu generic hoặc boxing, có thể khiến lời gọi mơ hồ hoặc tạo lỗi khó hiểu. Nên ưu tiên chữ ký đơn giản, kiểu tham số rõ và thông báo lỗi dễ hiểu.

## 7. Hằng số và enum trong DSL

Static import cũng có thể rút gọn việc tham chiếu hằng số hoặc enum constant. Điều này hữu ích khi DSL nội bộ biểu diễn trạng thái, toán tử hoặc đơn vị đo.

Ví dụ enum:

```java
package example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

Dùng tên đầy đủ:

```java
if (status == OrderStatus.PAID) {
    // xử lý đơn đã thanh toán
}
```

Dùng static import một hằng enum:

```java
import static example.orders.OrderStatus.PAID;

if (status == PAID) {
    // xử lý đơn đã thanh toán
}
```

Có thể import tất cả hằng enum:

```java
import static example.orders.OrderStatus.*;
```

Điều này giúp biểu thức ngắn hơn, nhưng nếu có nhiều enum cùng chứa tên `NEW`, `ACTIVE` hoặc `UNKNOWN`, nguồn gốc giá trị có thể khó nhận biết. Với các trạng thái quan trọng hoặc dễ trùng, giữ tên kiểu như `OrderStatus.PAID` thường rõ hơn.

## 8. Phạm vi và quy tắc phân giải tên

Static import chỉ có hiệu lực trong compilation unit chứa khai báo import. Nó không tự động truyền sang các tệp khác, package khác hoặc lớp gọi mã hiện tại.

Ví dụ:

```java
// OrderRules.java
import static example.rules.Conditions.equalTo;

class OrderRules {
    Condition condition = equalTo("status", "PAID");
}
```

Một tệp Java khác không thể dùng `equalTo(...)` chỉ vì `OrderRules.java` đã import nó. Tệp đó phải tự khai báo import hoặc dùng tên đầy đủ.

Khi phân giải tên, Java còn xem xét thành viên được khai báo trong kiểu hiện tại, thành viên kế thừa, import kiểu và các import static. Nếu tên bị trùng hoặc không thể xác định duy nhất, compiler có thể báo lỗi. Vì vậy, không nên coi static import là cơ chế tạo một không gian tên toàn cục cho DSL.

Một số quy tắc thực hành:

- Dùng import tường minh khi tên có ý nghĩa quan trọng hoặc dễ trùng.
- Giữ tên kiểu tại những nơi cần nhấn mạnh nguồn gốc của hằng số hoặc phương thức.
- Tránh import wildcard từ nhiều lớp DSL có nhiều tên chung.
- Không tạo phương thức static chỉ để né một lời gọi instance hợp lý.
- Khi IDE tự thêm import, vẫn cần kiểm tra xem tên được import có đúng miền và đúng ý nghĩa không.

## 9. Tên ngắn và khả năng đọc của DSL

Mục tiêu của DSL nội bộ là giúp ý định miền dễ nhận ra. Rút gọn cú pháp quá mức có thể làm mất thông tin cần thiết.

So sánh:

```java
rule("paid-order")
    .when(all(eq("status", "PAID"), gt("amount", 0)))
    .then(markEligible());
```

với:

```java
r("p").w(a(e("s", "P"), g("a", 0))).t(m());
```

Đoạn thứ hai ít ký tự hơn nhưng người đọc không thể nhận biết ngay các khái niệm. Tên ngắn chỉ có giá trị khi vẫn giữ được ý nghĩa và khả năng đọc.

### 9.1. Dùng tên theo vai trò

Trong một DSL khai báo quy tắc, có thể tổ chức tên theo vai trò:

| Vai trò | Tên ví dụ | Ý nghĩa |
|---|---|---|
| Bắt đầu khai báo | `rule` | Tạo một quy tắc |
| Điều kiện | `when` | Khai báo điều kiện áp dụng |
| Kết quả | `then` | Khai báo hành động khi điều kiện đúng |
| Kết hợp logic | `all`, `any`, `not` | Kết hợp biểu thức Boolean |
| So sánh | `equalTo`, `greaterThan` | Tạo điều kiện so sánh |
| Hành động | `markEligible`, `reject` | Tạo hành động thuộc miền |

Tên có thể gần với ngôn ngữ tự nhiên, nhưng không cần biến toàn bộ DSL thành một câu tiếng Anh dài. Mục tiêu là cấu trúc có thể đọc và hiểu được, không phải bắt chước văn xuôi.

### 9.2. Hạn chế trạng thái ẩn và tác dụng phụ

Các phương thức static dùng để tạo biểu thức nên có hành vi dễ dự đoán. Ví dụ `equalTo("status", "PAID")` nên trả về một điều kiện mô tả phép so sánh, không âm thầm đọc cơ sở dữ liệu hoặc thay đổi trạng thái toàn cục.

Factory method thuần (pure factory) thường giúp DSL dễ kiểm thử: cùng đầu vào tạo cùng mô tả, không phụ thuộc thứ tự gọi hoặc trạng thái ẩn. Các hành động có tác dụng phụ nên được biểu diễn rõ và chỉ thực thi ở giai đoạn runtime.

### 9.3. Giữ kiểu dữ liệu rõ ràng

Tên ngắn không nên đánh đổi khả năng kiểm tra kiểu. API generic và kiểu miền có thể giúp compiler phát hiện lỗi sớm:

```java
Condition<String> statusIsPaid = equalTo("status", "PAID");
Condition<Integer> retriesAllowed = lessThan("retryCount", 5);
```

Đây là cách biểu diễn khái niệm; kiểu cụ thể cần phù hợp với thiết kế thư viện. Nếu mọi giá trị đều bị chuyển thành `Object` quá sớm, DSL có thể mất một phần lợi ích kiểm tra tĩnh của Java.

## 10. Thiết kế API để static import hoạt động tốt

Để static import tạo ra DSL dễ dùng, lớp API cần được thiết kế có chủ đích.

### 10.1. Chỉ công khai các factory method cần thiết

Không nên đánh dấu mọi hàm trợ giúp là `public static`. Một số hàm chỉ phục vụ nội bộ và nên giữ package-private hoặc private. Bề mặt API công khai càng lớn thì khả năng xung đột tên và gánh nặng tương thích càng cao.

### 10.2. Dùng kiểu trả về có ý nghĩa

Thay vì trả về `Object` hoặc `String` cho mọi thao tác, nên dùng kiểu miền như `Condition`, `Action`, `RuleBuilder` hoặc `PipelineStep`. Kiểu trả về giúp người dùng nối lời gọi đúng và compiler kiểm tra cấu trúc.

### 10.3. Tránh tên chung chung ở lớp được import rộng

Các tên `create`, `get`, `value`, `of`, `run` thường dễ trùng. Nếu chúng xuất hiện trong nhiều nhóm DSL, nên dùng tên cụ thể hơn hoặc tách nhóm import. Có thể giữ tên ngắn ở facade chuyên biệt, nhưng phải đảm bảo ngữ cảnh đủ rõ.

### 10.4. Tài liệu hóa cách dùng dự kiến

Mỗi nhóm hàm static nên có ví dụ thể hiện cách import và cách kết hợp. Javadoc nên giải thích ý nghĩa miền, điều kiện hợp lệ, giá trị trả về và tác dụng phụ. Với DSL, ví dụ sử dụng thường quan trọng không kém chữ ký phương thức.

### 10.5. Kiểm thử ví dụ như mã người dùng thật

Các đoạn DSL trong tài liệu nên được biên dịch trong test hoặc sample project. Điều này giúp phát hiện khi một phương thức bị đổi tên, chữ ký thay đổi hoặc static import không còn hợp lệ.

## 11. Ví dụ minh họa đầy đủ về lớp DSL và cách sử dụng

Ví dụ sau tập trung vào hình thức API. Các lớp biểu diễn điều kiện và hành động được giản lược để làm nổi bật cách đặt tên và import.

```java
package example.dsl;

public final class TextConditions {
    private TextConditions() {}

    public static Condition contains(String field, String fragment) {
        return new TextCondition(field, "contains", fragment);
    }

    public static Condition startsWith(String field, String prefix) {
        return new TextCondition(field, "startsWith", prefix);
    }
}
```

Lớp điều kiện tổng hợp:

```java
package example.dsl;

public final class Conditions {
    private Conditions() {}

    public static Condition all(Condition... conditions) {
        return new AllCondition(conditions);
    }

    public static Condition any(Condition... conditions) {
        return new AnyCondition(conditions);
    }
}
```

Người dùng DSL:

```java
import static example.dsl.Conditions.all;
import static example.dsl.TextConditions.contains;
import static example.dsl.TextConditions.startsWith;

Condition customerFilter = all(
    contains("email", "@example.com"),
    startsWith("customerCode", "VIP-")
);
```

Các lớp `Condition`, `TextCondition`, `AllCondition` và `AnyCondition` là kiểu miền giả định, cần được định nghĩa trong một triển khai thực tế. Ví dụ cho thấy static import cho phép nhóm các hàm theo nguồn gốc lớp, nhưng người dùng vẫn viết biểu thức như một ngôn ngữ nhỏ trong Java.

## 12. Những sai lầm thường gặp

### 12.1. Import wildcard từ quá nhiều lớp

Khi nhiều lớp cùng cung cấp các hàm tên `of`, `value`, `all` hoặc `get`, wildcard làm mã khó truy vết và có thể gây lỗi phân giải tên. Hãy import chọn lọc hoặc gọi đầy đủ tên kiểu ở nơi cần thiết.

### 12.2. Đặt tên quá ngắn

Tên như `x`, `v`, `f`, `p` có thể khiến biểu thức khó hiểu khi không có ngữ cảnh đủ mạnh. Hãy ưu tiên từ ngắn nhưng quen thuộc và có nghĩa ổn định.

### 12.3. Nhầm static import với alias

Static import không đổi tên thành viên. Nếu API có tên không phù hợp với miền, hãy thiết kế wrapper hoặc đổi tên API một cách có chủ đích.

### 12.4. Biến mọi hàm thành static

Không phải thao tác nào cũng là factory. Nếu một hành động cần trạng thái của đối tượng, quyền truy cập hoặc phụ thuộc runtime, việc ép nó thành phương thức static có thể làm API khó kiểm soát và kiểm thử.

### 12.5. Dùng static import để che giấu nguồn gốc

Nếu tên `max`, `value` hoặc `of` xuất hiện trong nhiều miền, gọi trực tiếp có thể khiến người đọc không biết hàm nào đang được sử dụng. Hãy giữ tên lớp khi nguồn gốc có ý nghĩa.

### 12.6. Đánh đổi tính rõ ràng để lấy ít dòng mã

DSL nội bộ cần dễ đọc trong review, log và tài liệu. Một biểu thức ngắn nhưng cần tra nhiều lớp để hiểu có thể tốn nhiều công bảo trì hơn cách viết đầy đủ.

## 13. Hướng dẫn lựa chọn và quy ước thực hành

Khi thiết kế DSL nội bộ bằng Java, có thể áp dụng các quy ước sau:

1. Xác định khái niệm miền và cách diễn đạt mong muốn trước khi chọn tên phương thức.
2. Dùng phương thức `public static` cho các factory hoặc hàm tiện ích thực sự thuộc API công khai.
3. Gom hàm theo trách nhiệm miền để người dùng có thể import từ các lớp rõ nghĩa.
4. Ưu tiên import tường minh cho những tên quan trọng hoặc dễ trùng.
5. Dùng wildcard có giới hạn khi một lớp facade nhỏ và ổn định cung cấp một nhóm hàm nhất quán.
6. Chọn tên ngắn, quen thuộc và không mơ hồ; tránh viết tắt khó hiểu.
7. Dùng kiểu trả về miền và generic khi phù hợp để giữ kiểm tra tĩnh.
8. Giữ lời gọi có tác dụng phụ rõ ràng; factory tạo biểu thức nên dễ dự đoán.
9. Gọi đầy đủ tên kiểu khi điều đó giúp làm rõ nguồn gốc hoặc tránh xung đột.
10. Biên dịch và kiểm thử các ví dụ DSL trong tài liệu như một phần của kiểm thử API.

Static import nên là lựa chọn trình bày có chủ đích. Khi bỏ tên lớp khiến ý nghĩa khó hiểu, hãy giữ tên lớp. Khi tên đơn giản làm biểu thức miền rõ hơn, static import có thể cải thiện đáng kể cách đọc DSL.

## 14. Câu hỏi tự kiểm tra

1. `import static` trong Java có tác dụng gì? Nó khác gì với import kiểu thông thường?
2. Phân biệt static import một thành viên với static import on demand. Khi nào nên ưu tiên từng cách?
3. Vì sao static import không thể import một phương thức instance và không hỗ trợ alias?
4. Static import hỗ trợ DSL nội bộ như thế nào? Nó có làm thay đổi cú pháp hoặc ngữ nghĩa của Java không?
5. Phân biệt static import với fluent API qua một đoạn mã có cả lời gọi static và lời gọi instance.
6. Vì sao tên `x`, `v` hoặc `proc` thường không phù hợp cho API DSL dùng lâu dài?
7. Điều gì có thể xảy ra khi import wildcard từ nhiều lớp có các phương thức cùng tên?
8. Hãy thiết kế một lớp tiện ích có các phương thức static cho miền bạn biết, viết câu lệnh import và tạo một biểu thức DSL ngắn, dễ đọc.
