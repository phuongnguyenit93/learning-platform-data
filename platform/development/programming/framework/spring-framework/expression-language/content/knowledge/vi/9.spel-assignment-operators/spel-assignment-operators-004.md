# Điều kiện để property có thể ghi trong SpEL

Trong Spring Expression Language (SpEL), không phải mọi biểu thức đọc được một giá trị đều có thể dùng làm đích ghi. Muốn gán giá trị cho một property, SpEL cần xác định được đối tượng đích, tìm được cơ chế truy cập hỗ trợ ghi và chuyển đổi giá trị gán sang kiểu mà property chấp nhận.

Hiểu điều kiện ghi giúp tránh lỗi khi dùng toán tử gán hoặc Expression.setValue(...), đặc biệt với JavaBean chỉ có getter, object lồng nhau, class immutable, custom PropertyAccessor và dữ liệu có kiểu khác nhau.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt property đọc được và property ghi được.
- Hiểu vai trò của getter, setter, field và PropertyAccessor.
- Kiểm tra khả năng ghi bằng Expression.isWritable(...).
- Gán giá trị bằng Expression.setValue(...) hoặc toán tử = trong SpEL.
- Xử lý property lồng nhau và object trung gian null.
- Hiểu chuyển đổi kiểu khi gán và các lỗi có thể xảy ra.
- Chọn EvaluationContext phù hợp cho thao tác cập nhật.
- Giới hạn quyền ghi để tránh biểu thức không tin cậy thay đổi object ngoài dự kiến.

Bạn nên biết JavaBean, getter/setter, class và object, cách tạo SpelExpressionParser và cách dùng EvaluationContext.

## 2. Đọc được không có nghĩa là ghi được

Một property có thể hỗ trợ đọc nhưng không hỗ trợ ghi. Ví dụ:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

SpEL có thể đọc property name thông qua getter. Tuy nhiên, class này không có setter cho name và field không được cung cấp như một đích ghi hợp lệ bởi accessor đang dùng. Vì vậy, một biểu thức đọc được name không nhất thiết có thể gán giá trị cho nó.

Đây là khác biệt cốt lõi:

- **Readable:** PropertyAccessor có thể lấy giá trị property từ object.
- **Writable:** PropertyAccessor có thể ghi giá trị mới vào property của object.

Với JavaBean thông thường, cách dễ hiểu nhất để cung cấp khả năng ghi là có getter và setter phù hợp:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Khi đó property name vừa đọc được vừa ghi được qua JavaBean accessor mặc định.

## 3. PropertyAccessor quyết định khả năng ghi

SpEL không tự giả định mọi tên property đều có thể gán. Nó sử dụng các PropertyAccessor trong EvaluationContext để tìm cách truy cập object đích.

Một PropertyAccessor có thể hỗ trợ:

- Đọc property.
- Ghi property.
- Cả đọc và ghi.
- Chỉ một nhóm kiểu object hoặc tên property cụ thể.

Với StandardEvaluationContext, reflective property accessor mặc định hỗ trợ JavaBean property thông qua getter/setter và các field mà accessor có thể truy cập. Nếu ứng dụng bổ sung custom PropertyAccessor, khả năng ghi phụ thuộc vào cách accessor đó triển khai kiểm tra và thao tác ghi.

Về mặt hợp đồng, một PropertyAccessor cần báo khả năng ghi bằng canWrite(...) và thực hiện việc ghi bằng write(...). Nếu canWrite trả về false cho target và property đang xét, SpEL không thể dùng accessor đó để ghi property.

Điều này có nghĩa cùng một object có thể ghi được trong một EvaluationContext nhưng không ghi được trong context khác, nếu hai context có bộ PropertyAccessor khác nhau.

## 4. Điều kiện của JavaBean property

### 4.1. Có setter tương ứng

Với JavaBean thông thường, setter là cơ chế phổ biến để ghi property:

~~~java
public class Account {
    private int age;

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Property age có getter để đọc và setter để ghi. Tên method setAge tuân theo quy tắc JavaBean tương ứng với property age.

Ví dụ có thể ghi:

~~~java
Account account = new Account();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("age");

expression.setValue(account, 30);
~~~

Sau thao tác, account.getAge() trả về 30.

### 4.2. Getter-only property

Nếu class chỉ có getter:

~~~java
public class Account {
    private final String accountNumber;

    public Account(String accountNumber) {
        this.accountNumber = accountNumber;
    }

    public String getAccountNumber() {
        return accountNumber;
    }
}
~~~

accountNumber là property đọc được nhưng không có setter. Với reflective property accessor thông thường, đây không phải đích ghi hợp lệ. Gọi setValue(...) cho property này sẽ thất bại nếu không có accessor khác cung cấp khả năng ghi.

Không nên cố sửa class immutable bằng cách giả định SpEL sẽ thay đổi field final. Nếu object được thiết kế immutable, hãy tạo object mới bằng constructor hoặc factory trong Java rồi thay thế tham chiếu ở nơi phù hợp.

### 4.3. Field có thể truy cập

Ngoài JavaBean setter, reflective property accessor có thể truy cập field mà nó được phép đọc hoặc ghi. Vì vậy, một class có field phù hợp đôi khi có thể hỗ trợ ghi dù không có setter.

Tuy nhiên, field access phụ thuộc vào khả năng truy cập reflection, modifier của field, module/access restrictions và accessor đang dùng. Field final không phải đích ghi an toàn hoặc hợp lệ cho thao tác cập nhật thông thường. Với thiết kế ứng dụng, nên ưu tiên setter hoặc custom accessor có hợp đồng rõ ràng thay vì dựa vào việc ghi trực tiếp field.

### 4.4. Setter phải nhận kiểu phù hợp

Setter phải nhận được giá trị sau khi SpEL chuyển đổi kiểu. Ví dụ property age có kiểu int thì giá trị cuối cùng phải chuyển được sang int.

~~~java
public class Account {
    private int age;

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Nếu giá trị đầu vào không thể chuyển thành số nguyên, thao tác ghi sẽ phát sinh lỗi chuyển đổi. Ngoài ra, setter có thể tự thực hiện validation và ném exception nếu giá trị vi phạm quy tắc nghiệp vụ.

## 5. Kiểm tra property có thể ghi bằng isWritable

Expression cung cấp phương thức isWritable để kiểm tra biểu thức có thể dùng làm đích ghi với root object và context hiện tại hay không.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("name");

Person person = new Person();

if (expression.isWritable(person)) {
    expression.setValue(person, "An");
}
~~~

Nếu dùng EvaluationContext tường minh:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(person);

Expression expression = parser.parseExpression("name");

boolean writable =
    expression.isWritable(context, person);

if (writable) {
    expression.setValue(context, person, "An");
}
~~~

isWritable giúp kiểm tra trước khi ghi, đặc biệt khi property path được cấu hình động. Tuy nhiên, kết quả kiểm tra chỉ phản ánh context, target object và trạng thái tại thời điểm kiểm tra. Nó không bảo đảm thao tác ghi sau đó luôn thành công: setter vẫn có thể ném exception, dữ liệu có thể thay đổi hoặc conversion có thể thất bại.

Hãy coi isWritable là bước kiểm tra khả năng truy cập, không phải validation nghiệp vụ hoàn chỉnh.

## 6. Ghi giá trị bằng setValue

### 6.1. Ghi property đơn giản

Ví dụ đầy đủ:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Person person = new Person();

if (!expression.isWritable(person)) {
    throw new IllegalStateException("Property name is not writable");
}

expression.setValue(person, "An");

System.out.println(person.getName());
~~~

setValue nhận object đích và giá trị cần gán. SpEL tìm accessor thích hợp, thực hiện chuyển đổi kiểu nếu cần và gọi cơ chế ghi tương ứng.

### 6.2. Ghi với EvaluationContext

Có thể truyền context để kiểm soát PropertyAccessor và TypeConverter:

~~~java
Person person = new Person();

StandardEvaluationContext context =
    new StandardEvaluationContext(person);

Expression expression = parser.parseExpression("name");

expression.setValue(context, person, "An");
~~~

Cách này hữu ích khi ứng dụng có custom PropertyAccessor, custom TypeConverter hoặc các cấu hình truy cập khác nhau cho từng use case.

### 6.3. Dùng toán tử gán trong biểu thức

SpEL hỗ trợ toán tử gán =. Ví dụ:

~~~java
Expression assignment =
    parser.parseExpression("name = 'An'");

Object assignedValue = assignment.getValue(person);
~~~

Biểu thức vừa ghi property name vừa trả về giá trị được gán. Điều này khác với toán tử so sánh ==.

Có hai cách thao tác phổ biến:

- Parse property path rồi gọi setValue(...): phù hợp khi muốn thể hiện rõ đích ghi và giá trị được cung cấp từ Java.
- Parse biểu thức có toán tử =: phù hợp khi phép gán là một phần của expression được cấu hình.

Trong ứng dụng, setValue thường dễ kiểm soát hơn vì code Java thể hiện rõ property đích và giá trị đầu vào.

## 7. Điều kiện khi ghi property lồng nhau

Một property path có thể gồm nhiều tầng:

~~~text
address.city
~~~

Để ghi city, SpEL phải đi qua address trước. Vì vậy:

1. Root object phải tồn tại.
2. Property trung gian address phải đọc được để lấy object Address.
3. Object Address phải tồn tại, hoặc parser phải được cấu hình auto grow null references và có đủ thông tin để tạo nó.
4. Property cuối city phải ghi được qua accessor phù hợp.
5. Giá trị được gán phải chuyển đổi được sang kiểu của city.

Ví dụ:

~~~java
public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class Person {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Nếu address đã được khởi tạo:

~~~java
Person person = new Person();
person.setAddress(new Address());

Expression expression =
    parser.parseExpression("address.city");

expression.setValue(person, "Da Nang");
~~~

Nếu address là null, biểu thức không thể đi tiếp theo cách thông thường. Có thể bật auto grow null references:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, false);

ExpressionParser configuredParser =
    new SpelExpressionParser(configuration);

Expression expression =
    configuredParser.parseExpression("address.city");

Person person = new Person();
expression.setValue(person, "Da Nang");
~~~

Khả năng khởi tạo còn phụ thuộc kiểu Address có thể được tạo trong runtime hay không. Nếu Address là interface, abstract class hoặc cần constructor argument mà SpEL không có cách cung cấp, auto grow không thể tự suy ra instance phù hợp.

## 8. SimpleEvaluationContext và quyền ghi

StandardEvaluationContext cung cấp nhiều khả năng truy cập reflection, method, type và bean tùy cấu hình. Trong use case chỉ cần data binding, SimpleEvaluationContext giúp giới hạn tính năng.

Ví dụ context cho phép đọc và ghi property theo data-binding accessor:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Context chỉ đọc:

~~~java
SimpleEvaluationContext readOnlyContext =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Với read-only context, property có thể đọc nhưng thao tác ghi không được cấp quyền. Với read-write context, các property phù hợp với data-binding accessor có thể được ghi.

Lựa chọn context cần phản ánh đúng use case:

- Chỉ hiển thị hoặc kiểm tra dữ liệu: ưu tiên read-only.
- Cập nhật DTO theo biểu thức được kiểm soát: cân nhắc read-write data binding.
- Cần accessor hoặc resolver tùy chỉnh: cấu hình rõ từng capability cần thiết.
- Không đánh giá biểu thức không tin cậy bằng context có quyền rộng.

## 9. Chuyển đổi kiểu và validation khi ghi

Property có thể ghi nhưng giá trị đầu vào vẫn có thể không hợp lệ. SpEL dùng TypeConverter của EvaluationContext để chuyển đổi giá trị sang kiểu đích khi cần.

Ví dụ property age có kiểu int, còn giá trị được cung cấp dưới dạng chuỗi "30". Nếu conversion service đang dùng hỗ trợ chuyển đổi này, phép gán có thể thành công. Nếu chuỗi là "thirty", conversion sẽ thất bại.

Cần phân biệt ba lớp kiểm tra:

1. **Writable check:** accessor có thể ghi property hay không?
2. **Type conversion:** giá trị có chuyển được sang kiểu property không?
3. **Business validation:** giá trị có hợp lệ theo quy tắc ứng dụng không?

Ví dụ tuổi có thể chuyển thành số nguyên nhưng vẫn không hợp lệ nếu âm. SpEL không tự biết giới hạn tuổi nghiệp vụ; hãy validate ở setter, DTO validation hoặc service tương ứng.

Nếu setter ném exception, lỗi đó có thể xuất hiện trong quá trình evaluate/setValue. Hãy bắt và xử lý ở ranh giới phù hợp, đồng thời không che giấu nguyên nhân bằng cách bỏ qua mọi lỗi ghi.

## 10. Collection, Map và indexed property

Property không phải đích ghi duy nhất trong SpEL. Với accessor hỗ trợ tương ứng, biểu thức cũng có thể ghi phần tử theo index hoặc key.

Ví dụ List:

~~~text
items[0]
~~~

Ví dụ Map:

~~~text
settings['theme']
~~~

Các đích này có điều kiện riêng:

- List cần có index hợp lệ hoặc parser được cấu hình auto grow collections khi use case cho phép.
- Map cần hỗ trợ truy cập key và có thể thêm hoặc thay value theo accessor.
- Array có kích thước cố định; không thể tự tăng kích thước array như List.
- Phần tử lồng nhau có thể null, cần object trung gian tồn tại hoặc auto grow null references phù hợp.

Đừng suy luận rằng một property JavaBean writable thì mọi phần tử collection bên trong nó cũng writable. Hãy kiểm tra đúng expression đích bằng isWritable với object và context thực tế.

## 11. Custom PropertyAccessor

Khi object không tuân theo JavaBean hoặc ứng dụng cần giới hạn property được ghi, có thể triển khai custom PropertyAccessor.

Accessor cần xác định:

- Nó hỗ trợ kiểu target nào.
- Property name nào có thể đọc.
- Property name nào có thể ghi.
- Cách lấy giá trị.
- Cách cập nhật giá trị.
- Cách báo lỗi khi property không hợp lệ hoặc giá trị không phù hợp.

Về nguyên tắc, canWrite(...) chỉ trả true cho các trường hợp accessor thực sự có thể cập nhật. write(...) thực hiện việc cập nhật sau khi SpEL chọn accessor.

Ví dụ thiết kế: một DTO cấu hình chỉ cho phép cập nhật displayName và enabled. Custom accessor có thể từ chối mọi tên property khác, ngay cả khi object đích có thêm field nội bộ. Cách này tạo allowlist rõ ràng cho dữ liệu được phép sửa.

Sau khi đăng ký accessor trong EvaluationContext, hãy kiểm tra isWritable cho các property được phép và bị cấm, rồi kiểm thử cả thao tác ghi thành công lẫn lỗi.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Property đọc được nhưng setValue thất bại | Có getter nhưng không có setter hoặc accessor chỉ hỗ trợ đọc | Thêm setter phù hợp hoặc dùng accessor hỗ trợ ghi |
| isWritable trả false | Context không có accessor ghi cho target/property | Kiểm tra PropertyAccessor và loại EvaluationContext |
| Không ghi được property lồng nhau | Object trung gian null hoặc không đọc được | Khởi tạo object hoặc cấu hình auto grow phù hợp |
| Lỗi chuyển đổi kiểu | Giá trị không chuyển được sang kiểu đích | Truyền kiểu đúng hoặc cấu hình TypeConverter có kiểm soát |
| Setter ném exception | Validation hoặc logic trong setter từ chối giá trị | Kiểm tra điều kiện nghiệp vụ và xử lý lỗi rõ ràng |
| Property immutable không cập nhật được | Không có setter hoặc field không writable | Tạo object mới và thay thế tham chiếu |
| SimpleEvaluationContext không cho ghi | Đang dùng read-only data binding | Chọn read-write context nếu use case được phép cập nhật |
| Ghi được property ngoài dự kiến | Context/accessor cấp quyền quá rộng | Dùng DTO nhỏ và allowlist property |

Khi debug, kiểm tra theo thứ tự: root object, property path, isWritable, accessor, object trung gian, conversion và validation trong setter. Cách này giúp phân biệt lỗi quyền ghi với lỗi dữ liệu.

## 13. An toàn khi cho phép ghi bằng SpEL

Ghi property là một side effect: object trong bộ nhớ thay đổi sau khi biểu thức được đánh giá. Nếu biểu thức đến từ request hoặc cấu hình do người dùng bên ngoài kiểm soát, việc cho phép ghi tùy ý có thể làm thay đổi trạng thái không mong muốn.

Hãy áp dụng các nguyên tắc:

- Chỉ cho phép các property nằm trong allowlist.
- Dùng DTO nhỏ, tránh truyền entity graph hoặc service nhạy cảm làm root object.
- Ưu tiên SimpleEvaluationContext với data-binding capability tối thiểu.
- Không bật method resolver, bean resolver hoặc type/constructor access nếu không cần.
- Validate giá trị trước khi lưu vào hệ thống.
- Không chia sẻ object mutable đang được cập nhật giữa nhiều request mà không có cơ chế đồng bộ.
- Ghi log đủ để chẩn đoán nhưng tránh lộ dữ liệu nhạy cảm.
- Không dùng biểu thức không tin cậy để cập nhật property tùy ý.

Đặc biệt, isWritable không phải cơ chế bảo mật. Nó chỉ cho biết expression có thể ghi với accessor/context hiện tại; quyền được cấp vẫn phải được giới hạn từ thiết kế context và dữ liệu đầu vào.

## 14. Bài tập thực hành

1. Tạo class Person có name với getter và setter. Parse expression name, kiểm tra isWritable rồi setValue.
2. Xóa setter của name và quan sát isWritable cùng lỗi khi ghi.
3. Tạo class Account có age kiểu int. Gán một giá trị chuỗi có thể chuyển đổi, sau đó thử một chuỗi không hợp lệ.
4. Tạo property address.city với address ban đầu null. Thử ghi khi auto grow tắt và bật.
5. Tạo SimpleEvaluationContext read-only và read-write, so sánh khả năng đọc và ghi.
6. Tạo custom PropertyAccessor chỉ cho phép displayName và enabled.
7. Thử gán property không nằm trong allowlist và xác nhận accessor từ chối.
8. Viết test cho setter validation, null intermediate, conversion failure và property immutable.

## 15. Checklist trước khi ghi property

- [ ] Root object và property path có tồn tại không?
- [ ] Property cuối có setter hoặc cơ chế ghi hợp lệ không?
- [ ] PropertyAccessor hiện tại có hỗ trợ write không?
- [ ] Các property trung gian có thể đọc được và object trung gian đã tồn tại chưa?
- [ ] Nếu dùng auto grow, kiểu object có thể khởi tạo được không?
- [ ] Giá trị gán có chuyển đổi được sang kiểu đích không?
- [ ] Setter hoặc tầng nghiệp vụ có validation phù hợp không?
- [ ] isWritable đã được kiểm tra với đúng context và target chưa?
- [ ] EvaluationContext có chỉ cấp quyền ghi cần thiết không?
- [ ] Biểu thức có thể làm thay đổi trạng thái ngoài dự kiến không?

## 16. Kết luận

Một property chỉ ghi được khi EvaluationContext có PropertyAccessor hỗ trợ ghi cho target và property đó. Với JavaBean thông thường, setter là cơ chế phổ biến; field có thể truy cập hoặc custom accessor cũng có thể cung cấp khả năng ghi. Để cập nhật an toàn, hãy kiểm tra isWritable, dùng setValue với context phù hợp, bảo đảm object trung gian tồn tại, xử lý chuyển đổi kiểu và validation. Với dữ liệu không tin cậy, giới hạn property được phép ghi và ưu tiên context data-binding có quyền tối thiểu.