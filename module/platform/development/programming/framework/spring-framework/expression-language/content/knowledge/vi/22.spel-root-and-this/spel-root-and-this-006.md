# Tránh nhầm #this với #root trong SpEL

## 1. Vì sao cần phân biệt #this và #root?

Spring Expression Language (SpEL) cung cấp hai biến hệ thống để tham chiếu object trong quá trình đánh giá:

- `#root` là root context object, tức đối tượng gốc được dùng để đánh giá expression.
- `#this` là active evaluation object, tức đối tượng hiện tại mà SpEL đang xử lý tại vị trí expression đó.

Ở cấp expression thông thường, khi chưa có thao tác đổi context như selection hoặc projection, `#this` thường trùng với `#root`. Nhưng khi SpEL đi vào collection operation, `#this` chuyển sang phần tử hiện tại, còn `#root` vẫn giữ nguyên object gốc.

Đây là khác biệt quan trọng nhất:

| Biến | Phạm vi | Có thay đổi trong collection operation không? |
|---|---|---|
| `#root` | Root object ban đầu của lần đánh giá. | Không. |
| `#this` | Object hiện tại tại vị trí expression đang được đánh giá. | Có; trong selection/projection nó là phần tử hiện tại. |

Nếu dùng nhầm hai biến, expression có thể đọc property từ sai object, gọi method trên sai kiểu hoặc trả về kết quả không đúng với dữ liệu nghiệp vụ.

## 2. Root object trong EvaluationContext

Root object có thể được thiết lập khi tạo EvaluationContext:

```java
Order order = loadOrder();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
```

Trong expression, có thể truy cập property và method của root object trực tiếp:

```text
orderNumber
customer.name
canShip(2)
```

Hoặc chỉ rõ root bằng `#root`:

```text
#root.orderNumber
#root.customer.name
#root.canShip(2)
```

Hai cách tương đương khi expression đang ở cấp root. Dùng `#root` khi muốn nhấn mạnh rằng property hoặc method thuộc object gốc, nhất là khi biểu thức có thể đi vào collection operation và làm thay đổi `#this`.

Cũng có thể truyền root object khi gọi `getValue()`:

```java
Expression expression = parser.parseExpression("#root.orderNumber");

String number = expression.getValue(
        context, order, String.class);
```

Root object được truyền cho lần đánh giá này là object mà `#root` tham chiếu. Cách này hữu ích khi một parser/context được tái sử dụng với nhiều root object khác nhau.

## 3. #this ở cấp expression thông thường

Khi expression được đánh giá trực tiếp trên root object và chưa chuyển sang context con, `#this` thường là chính root object:

```java
Customer customer = loadCustomer();

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

String name = parser.parseExpression("#this.name")
        .getValue(context, String.class);

String rootName = parser.parseExpression("#root.name")
        .getValue(context, String.class);
```

Cả hai expression đều đọc property `name` của Customer.

Tên property không có tiền tố cũng được phân giải trên object hiện tại:

```text
name
#this.name
#root.name
```

Ở cấp ngoài cùng, ba cách trên có thể cho cùng kết quả. Tuy nhiên, khi biểu thức được lồng trong selection/projection, chỉ `#root` tiếp tục tham chiếu root ban đầu; `#this` và tên property không tiền tố sẽ theo object hiện tại.

## 4. #this thay đổi trong collection selection

Selection dùng cú pháp `.?[predicate]` để lọc phần tử. Trong predicate, `#this` là phần tử đang được kiểm tra.

Giả sử root object là Company, có property `employees` là List<Employee> và property `name` là tên công ty:

```java
public class Company {
    private String name;
    private List<Employee> employees;

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}

public class Employee {
    private String name;
    private String department;

    public String getName() {
        return name;
    }

    public String getDepartment() {
        return department;
    }
}
```

Muốn chọn nhân viên thuộc phòng ban IT:

```text
#root.employees.?[#this.department == 'IT']
```

Trong predicate:

- `#root` là Company.
- `#root.employees` lấy danh sách nhân viên từ Company.
- `#this` là từng Employee được kiểm tra.
- `#this.department` đọc phòng ban của Employee hiện tại.

Có thể viết ngắn hơn:

```text
employees.?[department == 'IT']
```

Vì tên property không tiền tố trong predicate được phân giải trên phần tử hiện tại. Dạng có `#root` và `#this` tường minh hơn khi cần đối chiếu dữ liệu giữa root object và phần tử.

## 5. Dùng #root và #this cùng lúc

Một trường hợp thường gặp là lọc collection theo dữ liệu của root object. Ví dụ, Company có property `preferredDepartment`; muốn chọn nhân viên thuộc phòng ban đó:

```text
#root.employees.?[#this.department == #root.preferredDepartment]
```

Ý nghĩa:

1. `#root.employees` lấy collection từ Company.
2. SpEL duyệt từng Employee.
3. `#this.department` đọc department của Employee hiện tại.
4. `#root.preferredDepartment` đọc department ưu tiên trên Company.
5. Chỉ Employee có hai giá trị bằng nhau được giữ lại.

Nếu viết nhầm `#this.preferredDepartment`, SpEL sẽ tìm property đó trên Employee. Nếu Employee không có property này, expression sẽ lỗi hoặc không đáp ứng ý định.

Ví dụ projection kết hợp dữ liệu root và phần tử:

```text
#root.employees.![#root.name + ': ' + #this.name]
```

Kết quả là danh sách nhãn kết hợp tên công ty với tên từng nhân viên.

## 6. #this thay đổi theo từng cấp projection lồng nhau

Projection dùng cú pháp `.![expression]` để biến đổi từng phần tử thành một giá trị mới. Khi projection lồng nhau, `#this` chuyển sang phần tử của collection bên trong.

Ví dụ, Company có Departments và mỗi Department có Employees:

```text
#root.departments.![#this.name + ': ' + #this.employees.![#this.name]]
```

Có hai cấp context:

- Trong projection ngoài, `#this` là Department hiện tại.
- Trong projection trong, `#this` là Employee hiện tại.

`#root` ở cả hai cấp vẫn là Company ban đầu.

Nếu cần lấy tên Department trong expression của projection trong, không thể giả định `#this` vẫn là Department; tại đó `#this` đã là Employee. Có thể thiết kế dữ liệu hoặc expression để đưa giá trị cha vào biến có tên trước khi chuyển sang collection con, hoặc tách phép tính thành các bước rõ ràng trong Java nếu logic quá phức tạp.

## 7. #this trong Map selection/projection

Khi selection hoặc projection chạy trên Map, SpEL xử lý từng entry kiểu `Map.Entry`. Vì vậy, `#this` là entry hiện tại chứ không phải trực tiếp value.

Ví dụ:

```java
Map<String, Integer> scores = Map.of(
        "Ada", 95,
        "Grace", 91);

context.setVariable("scores", scores);
```

Lấy tên các entry có điểm từ 90 trở lên:

```text
#scores.?[#this.value >= 90].![#this.key]
```

Trong selection và projection:

- `#root` vẫn là root context object của expression.
- `#this.key` là key của Map.Entry hiện tại.
- `#this.value` là value của Map.Entry hiện tại.

Nếu muốn lấy value, dùng:

```text
#scores.![#this.value]
```

Đừng viết `#this.name` nếu current object là Map.Entry và entry không có property `name`. Hãy xác định chính xác kiểu của active object trước khi truy cập property.

## 8. Biến #root, #this và biến do ứng dụng đăng ký

Biến hệ thống và biến do ứng dụng đăng ký có mục đích khác nhau:

| Cú pháp | Nguồn | Ý nghĩa |
|---|---|---|
| `#root` | SpEL cung cấp | Root context object. |
| `#this` | SpEL cung cấp | Active evaluation object. |
| `#customer` | Ứng dụng đăng ký | Giá trị được đăng ký bằng `setVariable("customer", ...)`. |
| `#threshold` | Ứng dụng đăng ký | Giá trị cấu hình hoặc dữ liệu bổ sung. |

Ví dụ:

```java
context.setVariable("threshold", 100);
context.setVariable("customer", customer);

List<?> result = parser.parseExpression(
        "#root.orders.?[#this.total >= #threshold and " +
        "#this.customerId == #customer.id]")
        .getValue(context, company, List.class);
```

Trong biểu thức, `#threshold` và `#customer` là các biến ứng dụng; `#root` là Company; `#this` là Order đang được kiểm tra. Không cần đăng ký `#root` hoặc `#this` bằng `setVariable()`.

Tên biến và tên function dùng chung namespace trong EvaluationContext. Tránh đăng ký biến trùng tên với function mà expression cần gọi.

## 9. Ví dụ kiểm thử để thấy rõ phạm vi

Có thể kiểm tra trực tiếp sự khác nhau giữa root và current object bằng JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class RootAndThisTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void rootStaysCompanyWhileThisChangesPerEmployee() {
        Company company = new Company("Acme", List.of(
                new Employee("Ada", "IT"),
                new Employee("Grace", "HR")));

        StandardEvaluationContext context =
                new StandardEvaluationContext(company);

        List<?> result = parser.parseExpression(
                "#root.employees.![#root.name + ': ' + #this.name]")
                .getValue(context, List.class);

        assertEquals(
                List.of("Acme: Ada", "Acme: Grace"),
                result);
    }

    @Test
    void selectionUsesThisForCurrentEmployee() {
        Company company = new Company("Acme", List.of(
                new Employee("Ada", "IT"),
                new Employee("Grace", "HR")));

        StandardEvaluationContext context =
                new StandardEvaluationContext(company);

        List<?> result = parser.parseExpression(
                "#root.employees.?[#this.department == 'IT']")
                .getValue(context, List.class);

        assertEquals(1, result.size());
        assertEquals("Ada",
                parser.parseExpression("name")
                        .getValue(
                                new StandardEvaluationContext(result.get(0)),
                                String.class));
    }
}
```

Ví dụ trên giả định các constructor của Company và Employee nhận những tham số tương ứng. Test projection chứng minh `#root.name` giữ giá trị Company trong khi `#this.name` thay đổi theo Employee. Test selection chứng minh predicate được đánh giá trên từng Employee.

## 10. Cách đọc một expression phức tạp

Khi gặp biểu thức có nhiều cấp, hãy đọc theo thứ tự:

1. Xác định object được truyền vào `getValue()` hoặc root của EvaluationContext. Đó là `#root`.
2. Tìm các selection `.?[...]` và projection `.![...]`.
3. Tại mỗi predicate/projection, xác định collection nào đang được duyệt.
4. Trong expression con của collection operation, `#this` là phần tử hoặc entry hiện tại.
5. Nếu collection operation lồng nhau, cập nhật lại ý nghĩa của `#this` cho cấp trong.
6. Dùng `#root` khi cần quay lại object gốc.
7. Dùng tên biến như `#threshold` cho dữ liệu ứng dụng đã đăng ký.
8. Kiểm tra kiểu của object hiện tại trước khi truy cập property hoặc gọi method.

Có thể tạm viết chú thích cho biểu thức để tránh nhầm phạm vi:

```text
#root.employees
    .?[#this.department == #root.preferredDepartment]
    .![#root.name + ': ' + #this.name]
```

Ở cả selection và projection trong ví dụ, `#this` là Employee hiện tại. `#root` vẫn là Company.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `#this.name` đọc nhầm tên | Active object đã chuyển từ root sang phần tử collection. | Xác định scope hiện tại; dùng `#root.name` nếu cần tên root. |
| `#root.department` không tồn tại | Root object không có property đó; property thuộc phần tử. | Dùng `#this.department` trong selection/projection. |
| Expression hoạt động bên ngoài nhưng lỗi trong projection | `#this` đã đổi kiểu sang phần tử collection. | Kiểm tra kiểu phần tử và viết lại property path. |
| Projection lồng nhau đọc sai property cha | `#this` trong projection trong là phần tử collection trong. | Dùng `#root` cho root hoặc đưa giá trị cha vào variable trước. |
| Dùng #root nhưng nhận object khác dự kiến | Root được truyền vào overload `getValue(context, root, type)` khác với object context ban đầu. | Kiểm tra overload và object root của lần đánh giá. |
| Map predicate không tìm thấy value | `#this` là Map.Entry. | Dùng `#this.key` và `#this.value`. |
| Dùng `#root` hoặc `#this` như biến ứng dụng | Nhầm biến hệ thống với variable đăng ký. | Không gọi `setVariable()` cho hai biến hệ thống. |
| Tên property không tiền tố trỏ sai object | Tên không tiền tố được giải quyết trên active object. | Viết `#root.property` hoặc `#this.property` tường minh. |
| Expression dài khó xác định scope | Có nhiều collection operation lồng nhau. | Tách expression hoặc dùng biến có tên, viết chú thích và kiểm thử từng phần. |

## 12. Quy trình kiểm thử #root và #this

1. Tạo root object có property dễ nhận biết, ví dụ tên Company là `Acme`.
2. Tạo các phần tử collection có property khác biệt, ví dụ tên Employee là `Ada` và `Grace`.
3. Dùng expression kết hợp `#root.name` và `#this.name` trong projection.
4. Xác nhận root value không thay đổi và current value đổi theo từng phần tử.
5. Thêm selection để kiểm tra predicate dùng `#this` trên đúng kiểu phần tử.
6. Thêm projection lồng nhau nếu ứng dụng có collection phân cấp; xác định lại scope ở mỗi cấp.
7. Với Map, kiểm tra `#this.key` và `#this.value`.
8. Thử truyền root object khác qua overload `getValue()` để xác nhận `#root` gắn với lần đánh giá hiện tại.
9. Kiểm tra null và object trung gian có thể null.
10. Chạy test với cùng EvaluationContext và root object như ứng dụng thực tế.

## 13. Ghi nhớ

- `#root` luôn tham chiếu root context object của lần đánh giá.
- `#this` tham chiếu object hiện tại tại vị trí expression đang chạy.
- Ở expression cấp ngoài, #this thường trùng với #root.
- Trong selection/projection, #this là phần tử hiện tại; trong Map operation, đó là Map.Entry.
- Projection/selection lồng nhau làm #this chuyển theo collection bên trong.
- Tên property không tiền tố được phân giải trên active object, nên có thể thay đổi ý nghĩa khi scope đổi.
- Dùng #root để truy cập object gốc từ bất kỳ cấp collection operation nào.
- Dùng biến có tên như #threshold cho dữ liệu ứng dụng đã đăng ký.
- Viết #root và #this tường minh trong expression phức tạp để giảm lỗi nhầm scope.

## Tài liệu tham khảo

- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
