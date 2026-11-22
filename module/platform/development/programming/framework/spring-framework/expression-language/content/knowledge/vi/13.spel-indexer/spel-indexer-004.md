# Indexer trên object có accessor tương ứng

## Mục tiêu

SpEL dùng toán tử chỉ số trong ngoặc vuông để truy cập phần tử của nhiều cấu trúc dữ liệu. Ngoài array, List, Collection, String và Map, SpEL còn hỗ trợ đọc property của một object bằng tên property trong ngoặc vuông. Từ Spring Framework 6.2, ứng dụng cũng có thể đăng ký IndexAccessor để định nghĩa cách lập chỉ mục cho một cấu trúc tùy chỉnh không triển khai java.util.Map.

Bài này tập trung vào cách chọn đúng accessor cho object, cách đăng ký IndexAccessor và cách đọc hoặc ghi dữ liệu bằng cú pháp chỉ số.

Sau bài này, bạn có thể:

- Dùng cú pháp ngoặc vuông để truy cập property của một object.
- Phân biệt object indexing với Map indexing và property navigation bằng dấu chấm.
- Hiểu vai trò của IndexAccessor và PropertyAccessor.
- Đăng ký ReflectiveIndexAccessor cho một cấu trúc tùy chỉnh.
- Xác định khi nào cần tự triển khai IndexAccessor hoặc CompilableIndexAccessor.
- Xử lý null, kiểu index không phù hợp và lỗi đọc/ghi.

## 1. Tổng quan về toán tử chỉ số

Cú pháp tổng quát:

~~~text
target[index]
~~~

Ý nghĩa của index phụ thuộc vào kiểu target:

| Target | Ý nghĩa của index | Ví dụ |
|---|---|---|
| Array | Vị trí phần tử, bắt đầu từ 0 | **items[0]** |
| List hoặc Collection | Vị trí phần tử, bắt đầu từ 0 | **members[1]** |
| String | Vị trí ký tự, kết quả là String | **name[0]** |
| Map | Khóa dùng để lấy value | **settings['theme']** |
| Object | Tên property cần đọc | **#root['name']** |
| Custom structure | Giá trị index do IndexAccessor đã đăng ký xử lý | **#fruitMap[T(example.Color).RED]** |

SpEL lựa chọn cách indexing dựa trên kiểu target và accessor tương ứng trong EvaluationContext. Vì thế, cùng cú pháp ngoặc vuông nhưng không phải lúc nào cũng có cùng ý nghĩa.

Các index số trong array, List, Collection và String là zero-based. Phần tử đầu tiên hoặc ký tự đầu tiên có index 0.

## 2. Indexing vào property của object

Với object thông thường, có thể lấy một property bằng cách đặt tên property trong dấu ngoặc vuông:

~~~text
#root['name']
~~~

Ví dụ Java:

~~~java
Inventor tesla = new Inventor("Nikola Tesla");

String name = parser.parseExpression("#root['name']")
    .getValue(context, tesla, String.class);
~~~

Kết quả là tên của inventor. Cú pháp này tương tự việc lấy value từ Map theo key, nhưng target ở đây là một object và chuỗi trong ngoặc vuông là tên property.

Nếu property name có thể truy cập qua PropertyAccessor của EvaluationContext, SpEL có thể đọc nó. Vì vậy, object indexing bằng tên property vẫn phụ thuộc vào khả năng đọc property của context.

### So sánh với dấu chấm

Hai cách sau thường truy cập cùng một property:

~~~text
#root.name
#root['name']
~~~

Dấu chấm phù hợp khi tên property đã biết rõ và cố định. Ngoặc vuông hữu ích khi muốn thể hiện property như một index hoặc khi tên property được tính động từ một biến:

~~~text
#root[#propertyName]
~~~

Trong ví dụ này, propertyName phải đánh giá thành String chứa tên property cần đọc. Nếu biến chưa được cung cấp, có kiểu không phù hợp hoặc tên property không được accessor hỗ trợ, biểu thức có thể thất bại.

Không nhầm object indexing với Map indexing. Nếu target thực sự là Map, biểu thức **settings['theme']** tìm key theme trong Map. Nếu target là một Java object, biểu thức **#root['name']** yêu cầu accessor đọc property name trên object đó.

## 3. PropertyAccessor và IndexAccessor

Hai loại accessor có mục đích khác nhau:

| Thành phần | Cú pháp tiêu biểu | Trách nhiệm |
|---|---|---|
| PropertyAccessor | **customer.name** | Đọc hoặc ghi property có tên trên object |
| IndexAccessor | **customer[index]** | Đọc hoặc ghi phần tử tại một index trên cấu trúc |
| Map indexing | **settings['theme']** | Lấy value theo key của Map |
| Object indexing | **#root['name']** | Lấy property của object bằng tên String |

PropertyAccessor nhận tên property dưới dạng String. IndexAccessor nhận index dưới dạng Object, vì index có thể là số, enum hoặc kiểu tùy chỉnh khác.

Đối với object indexing với index là tên property dạng String, SpEL có thể sử dụng cơ chế PropertyAccessor tương ứng để đọc property. Đối với một cấu trúc tùy chỉnh có cách lập chỉ mục riêng, ứng dụng cần đăng ký IndexAccessor phù hợp.

Không nên triển khai IndexAccessor chỉ để thay thế một PropertyAccessor đã có thể đọc property thông thường. Hãy chọn loại accessor theo ý nghĩa dữ liệu mà biểu thức cần truy cập.

## 4. Indexing vào custom structure

Một số class hoạt động giống Map hoặc bảng tra cứu nhưng không triển khai java.util.Map. Ví dụ, class có thể nhận một enum làm khóa và trả về một giá trị tương ứng:

~~~java
public enum Color {
    RED, ORANGE, YELLOW
}

public class FruitMap {
    private final Map<Color, String> map = new HashMap<>();

    public FruitMap() {
        this.map.put(Color.RED, "cherry");
        this.map.put(Color.ORANGE, "orange");
        this.map.put(Color.YELLOW, "banana");
    }

    public String getFruit(Color color) {
        return this.map.get(color);
    }

    public void setFruit(Color color, String fruit) {
        this.map.put(color, fruit);
    }
}
~~~

FruitMap có thể tra cứu theo Color nhưng không triển khai Map. SpEL không tự suy ra rằng Color là index và getFruit là phương thức đọc. Từ Spring Framework 6.2, có thể đăng ký một IndexAccessor để mô tả hợp đồng indexing đó.

Khi đã có accessor, biểu thức có thể dùng cú pháp:

~~~text
#fruitMap[T(example.Color).RED]
~~~

Biểu thức dùng enum RED làm index và lấy giá trị tương ứng từ FruitMap.

## 5. Dùng ReflectiveIndexAccessor

Spring cung cấp ReflectiveIndexAccessor để xử lý các cấu trúc tùy chỉnh phổ biến mà không cần tự viết một lớp IndexAccessor.

Constructor có ba tham số tạo accessor chỉ đọc:

~~~java
new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit"
)
~~~

Các tham số lần lượt là:

1. **targetType:** kiểu của object được lập chỉ mục, ở đây là FruitMap.
2. **indexType:** kiểu của index, ở đây là Color.
3. **readMethodName:** tên public method dùng để đọc, ở đây là getFruit.

Để hỗ trợ cả ghi, dùng constructor có thêm tên write method:

~~~java
new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit",
    "setFruit"
)
~~~

Read method nhận một đối số có kiểu Color và trả về String. Write method nhận cùng index Color cùng value String. Kiểu value của write method phải phù hợp với kiểu trả về của read method theo quy ước của ReflectiveIndexAccessor.

Các read/write method phải là public. Nếu bật SpEL compilation cho biểu thức đọc, method được cấu hình cũng cần có thể gọi thông qua một public class hoặc public interface.

### Đăng ký accessor và đọc index

Ví dụ đầy đủ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

IndexAccessor fruitMapAccessor = new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit",
    "setFruit"
);

context.addIndexAccessor(fruitMapAccessor);
context.setVariable("fruitMap", new FruitMap());

String fruit = parser
    .parseExpression("#fruitMap[T(example.Color).RED]")
    .getValue(context, String.class);
~~~

Kết quả là **cherry**.

Điểm quan trọng là accessor phải được đăng ký vào chính EvaluationContext được dùng khi đánh giá. Chỉ tạo đối tượng ReflectiveIndexAccessor mà không thêm nó vào context thì SpEL không thể sử dụng accessor đó.

### Ghi một index

Vì ví dụ đăng ký read-write accessor, có thể gán giá trị qua biểu thức:

~~~java
parser.parseExpression(
    "#fruitMap[T(example.Color).RED] = 'strawberry'"
).getValue(context);

String updatedFruit = parser
    .parseExpression("#fruitMap[T(example.Color).RED]")
    .getValue(context, String.class);
~~~

Sau phép gán, giá trị đọc lại cho Color.RED là strawberry.

Nếu chỉ cần đọc, nên dùng constructor ba tham số. Không cấp write method nếu nghiệp vụ không cần thay đổi cấu trúc dữ liệu.

## 6. Tự triển khai IndexAccessor

Khi cấu trúc không có read/write method theo quy ước mà ReflectiveIndexAccessor yêu cầu, có thể tự triển khai interface IndexAccessor.

Interface này định nghĩa bốn thao tác chính:

| Method | Trách nhiệm |
|---|---|
| **canRead(context, target, index)** | Xác định accessor có đọc được index trên target này không |
| **read(context, target, index)** | Đọc value và trả về TypedValue |
| **canWrite(context, target, index)** | Xác định accessor có ghi được index này không |
| **write(context, target, index, newValue)** | Ghi value mới vào index |

IndexAccessor cũng kế thừa TargetedAccessor. Phương thức getSpecificTargetClasses() cho phép khai báo những kiểu target mà accessor hỗ trợ. Accessor chỉ định rõ target class được ưu tiên thử trước các accessor tổng quát.

Quy trình sử dụng:

1. SpEL cung cấp EvaluationContext, target object và index.
2. Accessor được hỏi qua canRead hoặc canWrite.
3. Nếu accessor xác nhận có thể thực hiện thao tác, SpEL gọi read hoặc write với cùng các đối số.
4. read trả về TypedValue để giữ giá trị và thông tin kiểu.
5. Nếu không có accessor nào hỗ trợ thao tác, SpEL báo lỗi indexing tương ứng.

Hợp đồng rất quan trọng: read chỉ nên được gọi sau khi canRead trả về true cho cùng target và index. Tương tự, write chỉ nên được gọi sau khi canWrite trả về true.

Khi triển khai accessor riêng, cần xác định rõ:

- Kiểu target được hỗ trợ.
- Kiểu index được chấp nhận.
- Hành vi khi index không tồn tại.
- Kiểu value được trả về.
- Hành vi đọc và ghi khi dữ liệu null.
- Cách báo lỗi khi cấu trúc không cho phép thao tác.
- Quyền ghi có được hỗ trợ hay không.

Nếu accessor chỉ hỗ trợ một số class, hãy khai báo target class cụ thể. Tránh accessor tổng quát nhận mọi object rồi mới kiểm tra quá nhiều trường hợp trong mỗi lần đánh giá.

## 7. IndexAccessor và khả năng compilation

SpEL có thể biên dịch một số biểu thức thành bytecode để tối ưu việc đánh giá. Một custom IndexAccessor chỉ hỗ trợ giao diện IndexAccessor thì không mặc nhiên cung cấp thông tin cần thiết cho compilation.

Nếu muốn hỗ trợ compilation, accessor cần triển khai thêm CompilableIndexAccessor và cung cấp khả năng sinh bytecode theo SPI đó.

ReflectiveIndexAccessor đã triển khai CompilableIndexAccessor và hỗ trợ compilation cho read access khi đủ điều kiện. Tuy nhiên, read method được cấu hình phải có thể gọi qua một public class hoặc public interface để compilation thành công.

Không nên bật compilation chỉ vì accessor có hỗ trợ. Hãy đo hiệu năng với biểu thức và model thực tế, đồng thời kiểm thử cả chế độ thông dịch và chế độ biên dịch nếu ứng dụng sử dụng cả hai.

## 8. Safe indexing và object null

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe indexing bằng cú pháp **?.[ ]**:

~~~text
#fruitMap?.[T(example.Color).RED]
~~~

Nếu fruitMap là null, biểu thức trả về null thay vì cố thực hiện thao tác indexing trên null. Nếu fruitMap có giá trị, SpEL tiếp tục tìm IndexAccessor phù hợp và đọc index như bình thường.

Null-safe indexing hỗ trợ array, collection, string, map, object và custom structure.

Cần phân biệt hai điều kiện:

- **Target null:** safe indexing có thể trả về null.
- **Index hoặc accessor không hợp lệ:** safe indexing không sửa được kiểu index sai, accessor không hỗ trợ target hoặc lỗi bên trong read method.

Ví dụ, nếu FruitMap tồn tại nhưng index được truyền không phải Color như accessor yêu cầu, thao tác vẫn có thể thất bại. Safe indexing chỉ bảo vệ target null, không bỏ qua hợp đồng của accessor.

Với phiên bản Spring Framework trước 6.2, cú pháp null-safe indexing này chưa được hỗ trợ. Hãy xác nhận phiên bản framework trước khi dùng trong biểu thức.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Indexing không được hỗ trợ trên target | Không có IndexAccessor phù hợp hoặc target không thuộc kiểu được hỗ trợ | Kiểm tra target class và đăng ký accessor |
| Accessor không nhận index | Index có kiểu khác indexType | Kiểm tra biểu thức index và kiểu dữ liệu |
| Lỗi khi đọc index | Read method hoặc logic accessor phát sinh lỗi | Kiểm tra public read method, dữ liệu và thông báo exception |
| Lỗi khi ghi index | Không có write method hoặc write method không phù hợp | Dùng read-write accessor và kiểm tra chữ ký method |
| Accessor hoạt động trong context này nhưng không ở context khác | Chưa đăng ký accessor vào context đang dùng | Kiểm tra factory tạo EvaluationContext |
| Biểu thức trả null | Target null và đang dùng safe indexing, hoặc dữ liệu index không có value | Phân biệt target null với index không tồn tại |
| Compilation thất bại | Accessor không compilable hoặc read method không thể gọi qua public type | Dùng CompilableIndexAccessor và kiểm tra visibility |
| Indexer xử lý nhầm cấu trúc | Accessor tổng quát nhận quá nhiều target | Khai báo specific target classes và thu hẹp canRead |

Khi chẩn đoán, ghi nhận biểu thức, target class, index class, loại thao tác đọc/ghi và accessor được dùng. Không cần ghi toàn bộ nội dung object nếu nó chứa dữ liệu nhạy cảm.

## 10. Kiểm thử IndexAccessor

Với custom indexing, kiểm thử nên xác nhận cả việc accessor được chọn và giá trị trả về.

Các trường hợp cần có:

- Target thuộc kiểu được hỗ trợ và index hợp lệ.
- Target đúng kiểu nhưng index sai kiểu.
- Index hợp lệ nhưng không có value tương ứng.
- Target null với biểu thức thường và biểu thức null-safe.
- Accessor chỉ đọc và trường hợp cố gắng ghi.
- Accessor read-write và giá trị sau khi cập nhật.
- Nhiều accessor cùng tồn tại trong một context.
- Biểu thức được đánh giá trong context production tương đương.
- Compilation nếu ứng dụng bật SpEL compiler.

Ví dụ kiểm thử đọc và ghi với FruitMap:

~~~java
@Test
void indexesCustomFruitMap() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    context.addIndexAccessor(new ReflectiveIndexAccessor(
        FruitMap.class, Color.class, "getFruit", "setFruit"));

    context.setVariable("fruitMap", new FruitMap());

    Expression read = parser.parseExpression(
        "#fruitMap[T(example.Color).RED]");

    assertEquals("cherry", read.getValue(context, String.class));

    parser.parseExpression(
        "#fruitMap[T(example.Color).RED] = 'strawberry'")
        .getValue(context);

    assertEquals("strawberry", read.getValue(context, String.class));
}
~~~

Test nên dùng chính accessor factory mà ứng dụng triển khai, tránh tự dựng một context khác với production.

## 11. Thực hành tốt

- Dùng object indexing với tên String khi mục đích là đọc property của object.
- Dùng IndexAccessor khi cấu trúc có quy tắc index riêng và không phải Map/array/collection thông thường.
- Đăng ký accessor vào đúng EvaluationContext trước khi đánh giá.
- Chọn ReflectiveIndexAccessor khi cấu trúc có public read/write method theo quy ước phù hợp.
- Chỉ cấp write method khi biểu thức thực sự cần thay đổi dữ liệu.
- Khai báo target class và index type cụ thể để tránh accessor nhận nhầm object.
- Trả về TypedValue với thông tin kiểu phù hợp khi tự triển khai IndexAccessor.
- Triển khai CompilableIndexAccessor nếu cần compilation cho custom indexing.
- Dùng null-safe indexing chỉ khi target null là tình huống được chấp nhận.
- Kiểm thử index hợp lệ, index sai kiểu, target null, lỗi read/write và cấu hình context.
- Không cho phép biểu thức không đáng tin truy cập cấu trúc hoặc ghi dữ liệu ngoài phạm vi được phép.

## 12. Checklist review

Trước khi đưa một biểu thức custom indexing vào sử dụng, hãy kiểm tra:

- [ ] Target type và index type đã được xác định.
- [ ] Cú pháp ngoặc vuông phù hợp với loại target.
- [ ] Object indexing dùng tên property có thể đọc được.
- [ ] Custom structure đã có IndexAccessor tương ứng.
- [ ] Accessor đã được đăng ký trong EvaluationContext đang đánh giá.
- [ ] canRead/read và canWrite/write tuân thủ cùng hợp đồng target/index.
- [ ] Read/write method là public nếu dùng ReflectiveIndexAccessor.
- [ ] Write access chỉ được bật khi cần thiết.
- [ ] Null-safe indexing chỉ được dùng để xử lý target null.
- [ ] Có kiểm thử giá trị đọc, cập nhật, index sai kiểu và lỗi accessor.
- [ ] Compilation được kiểm tra nếu ứng dụng dùng SpEL compiler.

## Kết luận

SpEL hỗ trợ indexing vào object bằng tên property trong ngoặc vuông và hỗ trợ custom structure thông qua IndexAccessor. Object indexing vẫn cần PropertyAccessor đọc được property tương ứng; custom indexing cần accessor được đăng ký trong EvaluationContext. Từ Spring Framework 6.2, ReflectiveIndexAccessor giúp nối cú pháp ngoặc vuông với public read/write method của một cấu trúc tùy chỉnh. Hãy xác định rõ target, index, quyền đọc/ghi và hành vi null, sau đó kiểm thử trong đúng context của ứng dụng.
